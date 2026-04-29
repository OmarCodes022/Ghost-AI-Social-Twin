"""ghost_webhook_receiver

Handles the two WhatsApp webhook endpoints:

  GET  /webhook  — token verification challenge (Meta Cloud API handshake)
  POST /webhook  — inbound message notifications

On POST the handler parses each text message from the payload and invokes
``ghost-orchestrator-{env}`` asynchronously (InvocationType=Event) so the
API Gateway response is returned in < 500 ms as Meta requires.
"""
import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import boto3

from models import InboundWhatsAppMessage, OrchestratorEvent
from ssm import get_parameter

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_lambda_client: Any = None


def _get_lambda_client():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda")
    return _lambda_client


# ─── Entry point ──────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context: Any) -> dict:
    method = event.get("httpMethod", "")
    logger.info(
        json.dumps({"event": "request_received", "method": method, "path": event.get("path")})
    )

    if method == "GET":
        return _handle_verification(event)
    if method == "POST":
        return _handle_webhook(event)

    return {"statusCode": 405, "body": "Method Not Allowed"}


# ─── GET: verification handshake ──────────────────────────────────────────────

def _handle_verification(event: dict) -> dict:
    params = event.get("queryStringParameters") or {}
    mode = params.get("hub.mode", "")
    token = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge", "")

    env = os.environ.get("ENV", "dev")
    expected_token = get_parameter(f"/ghost/{env}/whatsapp/verify_token")

    if mode == "subscribe" and token == expected_token:
        logger.info(json.dumps({"event": "webhook_verified"}))
        return {"statusCode": 200, "body": challenge}

    logger.warning(
        json.dumps({"event": "webhook_verification_failed", "mode": mode})
    )
    return {"statusCode": 403, "body": "Forbidden"}


# ─── POST: inbound message ─────────────────────────────────────────────────────

def _handle_webhook(event: dict) -> dict:
    body_str: str = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body_str = base64.b64decode(body_str).decode("utf-8")

    try:
        body = json.loads(body_str)
    except json.JSONDecodeError:
        logger.error(json.dumps({"event": "invalid_json_body"}))
        return {"statusCode": 400, "body": "Invalid JSON"}

    messages = _extract_text_messages(body)

    for msg in messages:
        _invoke_orchestrator_async(msg)

    # Meta expects a 200 quickly; any non-200 triggers retries.
    return {"statusCode": 200, "body": "OK"}


def _extract_text_messages(body: dict) -> list[InboundWhatsAppMessage]:
    result: list[InboundWhatsAppMessage] = []

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            for msg in value.get("messages", []):
                if msg.get("type") != "text":
                    logger.info(
                        json.dumps(
                            {"event": "non_text_message_skipped", "type": msg.get("type")}
                        )
                    )
                    continue

                phone_number: str = msg.get("from", "")
                message_id: str = msg.get("id", "")
                content: str = msg.get("text", {}).get("body", "")
                ts_unix = int(msg.get("timestamp", 0))
                timestamp = datetime.fromtimestamp(ts_unix, tz=timezone.utc)

                result.append(
                    InboundWhatsAppMessage(
                        phone_number=phone_number,
                        message_id=message_id,
                        content=content,
                        timestamp=timestamp,
                        raw_payload=msg,
                    )
                )

    return result


def _invoke_orchestrator_async(message: InboundWhatsAppMessage) -> None:
    env = os.environ.get("ENV", "dev")
    function_name = f"ghost-orchestrator-{env}"

    payload = OrchestratorEvent(inbound_message=message).model_dump(mode="json")

    _get_lambda_client().invoke(
        FunctionName=function_name,
        InvocationType="Event",  # fire-and-forget
        Payload=json.dumps(payload).encode(),
    )

    logger.info(
        json.dumps(
            {
                "event": "orchestrator_invoked",
                "phone": message.phone_number,
                "message_id": message.message_id,
            }
        )
    )
