import base64
import json
import logging
import os
from datetime import datetime, timezone

import boto3

from ssm import get_parameter

log = logging.getLogger(__name__)
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_sqs = None


def _get_sqs():
    global _sqs
    if not _sqs:
        _sqs = boto3.client("sqs", region_name=os.environ["AWS_REGION"])
    return _sqs


def lambda_handler(event, context):
    method = event.get("httpMethod", "")
    if method == "GET":
        return _verify(event)
    if method == "POST":
        return _ingest(event)
    return {"statusCode": 405, "body": "Method Not Allowed"}


def _verify(event):
    params = event.get("queryStringParameters") or {}
    mode = params.get("hub.mode", "")
    token = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge", "")

    expected = get_parameter(f"/ghost/{os.environ['ENV']}/whatsapp/verify_token")
    if mode == "subscribe" and token == expected:
        log.info("webhook verified")
        return {"statusCode": 200, "body": challenge}

    log.warning("webhook verification failed - bad token or mode")
    return {"statusCode": 403, "body": "Forbidden"}


def _ingest(event):
    body_str = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body_str = base64.b64decode(body_str).decode("utf-8")

    try:
        body = json.loads(body_str)
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": "Invalid JSON"}

    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts_by_phone = {
                c["wa_id"]: c.get("profile", {}).get("name", "Unknown")
                for c in value.get("contacts", [])
            }
            for msg in value.get("messages", []):
                _enqueue(msg, contacts_by_phone)

    return {"statusCode": 200, "body": "OK"}


def _enqueue(msg: dict, contacts_by_phone: dict) -> None:
    msg_type = msg.get("type", "text")
    phone = msg.get("from", "")
    name = contacts_by_phone.get(phone, "Unknown")

    if msg_type == "text":
        content = msg.get("text", {}).get("body", "")
    elif msg_type in ("image", "video", "document", "sticker"):
        content = f"[{msg_type}]"
        msg_type = "media"
    elif msg_type == "audio":
        content = "[voice_note]"
        msg_type = "voice_note"
    else:
        log.info("skipping unsupported message type: %s", msg_type)
        return

    ts = datetime.fromtimestamp(int(msg.get("timestamp", 0)), tz=timezone.utc).isoformat()

    payload = {
        "phone_number": phone,
        "name": name,
        "whatsapp_message_id": msg.get("id", ""),
        "content": content,
        "timestamp": ts,
        "message_type": msg_type,
    }

    _get_sqs().send_message(
        QueueUrl=os.environ["INBOUND_QUEUE_URL"],
        MessageBody=json.dumps(payload),
    )
    log.info("enqueued message %s from %s", msg.get("id"), phone)
