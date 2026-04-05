"""Downstream invocations: SQS delay queue, WhatsApp sender, SNS escalation."""
import json
import logging
import os
import uuid
from typing import Any

import boto3

from db import get_cursor
from models import OrchestratorEvent, TelegramEscalationEvent, WhatsAppSenderRequest

logger = logging.getLogger(__name__)

_lambda_client: Any = None
_sns_client: Any = None
_sqs_client: Any = None


def get_lambda_client():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda")
    return _lambda_client


def get_sns_client():
    global _sns_client
    if _sns_client is None:
        _sns_client = boto3.client("sns")
    return _sns_client


def get_sqs_client():
    global _sqs_client
    if _sqs_client is None:
        _sqs_client = boto3.client("sqs")
    return _sqs_client


def enqueue_delay(orch_event: OrchestratorEvent, delay_seconds: int, reason: str) -> None:
    queue_url = os.environ.get("DELAY_QUEUE_URL", "")
    delayed_event = orch_event.model_copy(update={"is_delayed": True})
    get_sqs_client().send_message(
        QueueUrl=queue_url,
        MessageBody=delayed_event.model_dump_json(),
        DelaySeconds=min(delay_seconds, 900),
    )
    logger.info(json.dumps({"event": "reply_enqueued", "delay_seconds": delay_seconds, "reason": reason}))


def invoke_whatsapp_sender(
    env: str,
    to_phone_number: str,
    message: str,
    message_id: str | None,
    part_index: int = 0,
    inbound_message_id: str | None = None,
    reply_to_message_id: str | None = None,
) -> None:
    request = WhatsAppSenderRequest(
        to_phone_number=to_phone_number,
        message=message,
        message_id=message_id,
        part_index=part_index,
        inbound_message_id=inbound_message_id,
        reply_to_message_id=reply_to_message_id,
    )
    get_lambda_client().invoke(
        FunctionName=f"ghost-whatsapp-sender-{env}",
        InvocationType="Event",
        Payload=json.dumps(request.model_dump()).encode(),
    )


def publish_escalation(contact, original_message: str, proposed_reply: str, reason: str, message_id: str) -> None:
    topic_arn = os.environ.get("ESCALATIONS_TOPIC_ARN", "")
    escalation_id = str(uuid.uuid4())

    payload = TelegramEscalationEvent(
        escalation_id=escalation_id,
        message_id=message_id,
        contact_phone=contact.phone_number,
        contact_name=contact.name,
        original_message=original_message,
        proposed_reply=proposed_reply,
        reason=reason,
        confidence=1.0,
    )

    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO escalations (id, message_id, reason, confidence) VALUES (%s, %s, %s, %s)",
            (escalation_id, message_id, reason, 1.0),
        )

    get_sns_client().publish(TopicArn=topic_arn, Message=payload.model_dump_json())
    logger.info(json.dumps({"event": "escalation_published", "escalation_id": escalation_id}))
