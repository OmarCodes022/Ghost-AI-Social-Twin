import json
import logging
import os
from datetime import datetime, timezone

import boto3

from .classifier import classify
from .db import get_or_create_conversation, mark_processed, save_message, upsert_contact
from .models import InboundMessage, PerceptionOutput

log = logging.getLogger(__name__)
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "eu-west-1"))


def _perception_queue_url() -> str:
    return os.environ["PERCEPTION_OUTPUT_QUEUE_URL"]


def _escalation_queue_url() -> str:
    return os.environ["ESCALATION_QUEUE_URL"]


def lambda_handler(event, context):
    for record in event["Records"]:
        _process(json.loads(record["body"]))


def _process(raw: dict) -> None:
    msg = InboundMessage(**raw)
    log.info("processing message from %s", msg.phone_number)

    upsert_contact(msg.phone_number, msg.name)
    conv_id = get_or_create_conversation(msg.phone_number)
    message_id = save_message(conv_id, msg.phone_number, msg.content, msg.whatsapp_message_id)

    if not message_id:
        log.info("duplicate whatsapp_message_id %s — skipping", msg.whatsapp_message_id)
        return

    classification = classify(msg.content, msg.name)
    log.info("classified: %s", classification.model_dump())

    mark_processed(message_id)

    if classification.escalate:
        _sqs.send_message(
            QueueUrl=_escalation_queue_url(),
            MessageBody=json.dumps({
                "contact_phone": msg.phone_number,
                "message_id": message_id,
                "content": msg.content,
                "reason": classification.notes,
            }),
        )
        log.info("escalated message %s", message_id)
        return

    if not classification.needs_response:
        log.info("no response needed for message %s", message_id)
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
        QueueUrl=_perception_queue_url(),
        MessageBody=output.model_dump_json(),
    )
    log.info("routed message %s to ghost", message_id)
