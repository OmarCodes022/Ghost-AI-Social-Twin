import json
import logging
import os
from datetime import datetime, timezone

import boto3

from .classifier import classify
from .db import (
    get_or_create_conversation,
    save_message,
    upsert_contact,
    write_attitude_shift,
)
from .models import InboundMessage, PerceptionOutput

log = logging.getLogger(__name__)
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "eu-west-1"))

_HIGH_RISK_FLAGS = {"suicidal", "crisis", "threat", "medical_emergency"}


def lambda_handler(event, context):
    for record in event["Records"]:
        _process(json.loads(record["body"]))


def _process(raw: dict) -> None:
    msg = InboundMessage(**raw)
    log.info("processing message from %s", msg.phone_number)

    upsert_contact(msg.phone_number, msg.name)
    conv_id = get_or_create_conversation(msg.phone_number)
    message_id = save_message(
        conv_id,
        msg.phone_number,
        msg.content,
        msg.whatsapp_message_id,
    )

    if not message_id:
        log.info("duplicate whatsapp_message_id %s — skipping", msg.whatsapp_message_id)
        return

    classification = classify(msg.content, msg.name)
    log.info("classified: %s", classification.model_dump())

    write_attitude_shift(msg.phone_number, classification.attitude_shift)

    # Update message with detected language
    from .db import _get_conn
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE messages SET language = %s WHERE id = %s",
            (classification.language, message_id),
        )
    conn.commit()

    high_risk = set(classification.sensitivity_flags) & _HIGH_RISK_FLAGS
    if high_risk:
        _sqs.send_message(
            QueueUrl=os.environ["ESCALATION_QUEUE_URL"],
            MessageBody=json.dumps({
                "contact_phone": msg.phone_number,
                "contact_name": msg.name,
                "message_id": message_id,
                "content": msg.content,
                "reason": f"sensitivity_flags: {', '.join(high_risk)}",
            }),
        )
        log.info("escalated message %s (flags: %s)", message_id, high_risk)
        return

    output = PerceptionOutput(
        contact_phone=msg.phone_number,
        conversation_id=conv_id,
        message_id=message_id,
        content=msg.content,
        classification=classification,
        triggered_at=datetime.now(timezone.utc).isoformat(),
    )

    _sqs.send_message(
        QueueUrl=os.environ["PERCEPTION_OUTPUT_QUEUE_URL"],
        MessageBody=output.model_dump_json(),
    )
    log.info("routed message %s to ghost", message_id)
