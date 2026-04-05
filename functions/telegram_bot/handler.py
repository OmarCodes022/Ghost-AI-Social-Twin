"""ghost_telegram_bot

Two entry points in one Lambda:

  1. SNS event  — receives escalation, sends Telegram notification with buttons
  2. API Gateway POST /telegram — receives Telegram webhook updates:
       • callback_query  — button press (Send / Edit / Skip)
       • message         — text message from you (used as edited reply after pressing Edit)

Button callback_data format:  "send:{escalation_id}" | "edit:{escalation_id}" | "skip:{escalation_id}"

Edit flow:
  Press Edit → bot removes buttons, sends a force_reply prompt with the proposed text
  You reply with your edited version → bot sends it to WhatsApp, marks escalation resolved
"""
import json
import logging
import os
from typing import Any

import boto3
import requests

from db import get_cursor
from models import TelegramEscalationEvent, WhatsAppSenderRequest
from ssm import get_parameter

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_bot_token: str | None = None
_chat_id: str | None = None
_lambda_client: Any = None


def _get_bot_token() -> str:
    global _bot_token
    if _bot_token is None:
        env = os.environ.get("ENV", "dev")
        _bot_token = get_parameter(f"/ghost/{env}/telegram/bot_token")
    return _bot_token


def _get_chat_id() -> str:
    global _chat_id
    if _chat_id is None:
        env = os.environ.get("ENV", "dev")
        _chat_id = get_parameter(f"/ghost/{env}/telegram/chat_id")
    return _chat_id


def _get_lambda_client():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda")
    return _lambda_client


# ─── Entry point ──────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context: Any) -> dict:
    if "Records" in event:
        return _handle_sns(event)
    if "body" in event:
        return _handle_webhook(event)
    return {"statusCode": 400, "body": "Unknown event type"}


# ─── SNS: send escalation notification ───────────────────────────────────────

def _handle_sns(event: dict) -> dict:
    for record in event.get("Records", []):
        sns = record.get("Sns", {})
        try:
            body = json.loads(sns.get("Message", "{}"))
            escalation = TelegramEscalationEvent(**body)
            _send_escalation_notification(escalation)
        except Exception as exc:
            logger.error(json.dumps({
                "event": "escalation_notification_failed",
                "error": str(exc),
                "sns_message_id": sns.get("MessageId"),
            }))
            raise
    return {"statusCode": 200}


def _send_escalation_notification(escalation: TelegramEscalationEvent) -> None:
    contact = escalation.contact_name or escalation.contact_phone
    confidence_pct = f"{escalation.confidence:.0%}"

    text = (
        f"*Ghost Escalation*\n\n"
        f"*From:* {contact}\n"
        f"*Their message:*\n_{_esc(escalation.original_message)}_\n\n"
        f"*Proposed reply:*\n_{_esc(escalation.proposed_reply)}_\n\n"
        f"*Reason:* {escalation.reason}\n"
        f"*Confidence:* {confidence_pct}"
    )

    keyboard = {"inline_keyboard": [[
        {"text": "Send",  "callback_data": f"send:{escalation.escalation_id}"},
        {"text": "Edit",  "callback_data": f"edit:{escalation.escalation_id}"},
        {"text": "Skip",  "callback_data": f"skip:{escalation.escalation_id}"},
    ]]}

    result = _telegram("sendMessage", {
        "chat_id": _get_chat_id(),
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(keyboard),
    })

    logger.info(json.dumps({
        "event": "escalation_notification_sent",
        "escalation_id": escalation.escalation_id,
        "telegram_message_id": str(result.get("result", {}).get("message_id", "")),
    }))


# ─── API Gateway: Telegram webhook ────────────────────────────────────────────

def _handle_webhook(event: dict) -> dict:
    body_str = event.get("body") or "{}"
    try:
        update = json.loads(body_str)
    except json.JSONDecodeError:
        return {"statusCode": 400, "body": "bad json"}

    if "callback_query" in update:
        _handle_callback(update["callback_query"])
    elif "message" in update:
        _handle_message(update["message"])

    return {"statusCode": 200, "body": "ok"}


# ─── Callback: button press ───────────────────────────────────────────────────

def _handle_callback(cq: dict) -> None:
    callback_id = cq["id"]
    data = cq.get("data", "")
    tg_message = cq.get("message", {})
    tg_message_id = tg_message.get("message_id")

    if ":" not in data:
        _answer_callback(callback_id, "Unknown action")
        return

    action, escalation_id = data.split(":", 1)

    if action == "send":
        _action_send(escalation_id, callback_id, tg_message_id)
    elif action == "skip":
        _action_skip(escalation_id, callback_id, tg_message_id)
    elif action == "edit":
        _action_edit(escalation_id, callback_id, tg_message_id)
    else:
        _answer_callback(callback_id, "Unknown action")


def _action_send(escalation_id: str, callback_id: str, tg_message_id: int | None) -> None:
    row = _get_escalation(escalation_id)
    if not row:
        _answer_callback(callback_id, "Escalation not found")
        return

    _invoke_whatsapp_sender(row["contact_phone"], row["proposed_reply"], escalation_id)
    _resolve_escalation(escalation_id, "sent")
    _answer_callback(callback_id, "Sent")

    if tg_message_id:
        _remove_buttons(tg_message_id, suffix="\n\n✅ *Sent*")

    logger.info(json.dumps({"event": "escalation_sent", "escalation_id": escalation_id}))


def _action_skip(escalation_id: str, callback_id: str, tg_message_id: int | None) -> None:
    _resolve_escalation(escalation_id, "skipped")
    _answer_callback(callback_id, "Skipped")

    if tg_message_id:
        _remove_buttons(tg_message_id, suffix="\n\n⏭️ *Skipped*")

    logger.info(json.dumps({"event": "escalation_skipped", "escalation_id": escalation_id}))


def _action_edit(escalation_id: str, callback_id: str, tg_message_id: int | None) -> None:
    row = _get_escalation(escalation_id)
    if not row:
        _answer_callback(callback_id, "Escalation not found")
        return

    _answer_callback(callback_id, "Edit mode")

    if tg_message_id:
        _remove_buttons(tg_message_id, suffix="\n\n✏️ *Editing — reply below*")

    # Send a force_reply prompt with the proposed text so you can edit it inline
    _telegram("sendMessage", {
        "chat_id": _get_chat_id(),
        "text": f"✏️ Edit and send your reply for *{row['contact_phone']}*:\n\n`{_esc(row['proposed_reply'])}`",
        "parse_mode": "Markdown",
        "reply_markup": json.dumps({"force_reply": True, "selective": False}),
    })

    logger.info(json.dumps({"event": "escalation_edit_requested", "escalation_id": escalation_id}))


# ─── Message: edited reply from you ──────────────────────────────────────────

def _handle_message(message: dict) -> None:
    text = message.get("text", "").strip()
    if not text or text.startswith("/"):
        return

    # Find the most recent unresolved escalation
    row = _get_pending_escalation()
    if not row:
        _telegram("sendMessage", {
            "chat_id": _get_chat_id(),
            "text": "No pending escalation to send.",
        })
        return

    _invoke_whatsapp_sender(row["contact_phone"], text, str(row["escalation_id"]))
    _resolve_escalation(str(row["escalation_id"]), "edited")

    _telegram("sendMessage", {
        "chat_id": _get_chat_id(),
        "text": f"✅ Edited reply sent to {row['contact_phone']}",
    })

    logger.info(json.dumps({
        "event": "escalation_edited_sent",
        "escalation_id": str(row["escalation_id"]),
        "contact": row["contact_phone"],
    }))


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _get_escalation(escalation_id: str) -> dict | None:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT e.id as escalation_id, m.content as proposed_reply, conv.contact_phone
            FROM escalations e
            JOIN messages m ON m.id = e.message_id
            JOIN conversations conv ON conv.id = m.conversation_id
            WHERE e.id = %s AND e.resolved_at IS NULL
            """,
            (escalation_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _get_pending_escalation() -> dict | None:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT e.id as escalation_id, m.content as proposed_reply, conv.contact_phone
            FROM escalations e
            JOIN messages m ON m.id = e.message_id
            JOIN conversations conv ON conv.id = m.conversation_id
            WHERE e.resolved_at IS NULL
            ORDER BY m.sent_at DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _resolve_escalation(escalation_id: str, resolution: str) -> None:
    with get_cursor() as cur:
        cur.execute(
            "UPDATE escalations SET resolution = %s, resolved_at = NOW() WHERE id = %s",
            (resolution, escalation_id),
        )


# ─── Telegram API helpers ─────────────────────────────────────────────────────

def _telegram(method: str, payload: dict) -> dict:
    token = _get_bot_token()
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/{method}",
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _answer_callback(callback_id: str, text: str = "") -> None:
    _telegram("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})


def _remove_buttons(tg_message_id: int, suffix: str = "") -> None:
    """Remove the inline keyboard from a message, keeping its original text intact.

    Sends the status as a new message below rather than overwriting the original,
    so the full escalation details (contact, message, proposed reply, reason) stay visible.
    """
    chat_id = _get_chat_id()
    try:
        _telegram("editMessageReplyMarkup", {
            "chat_id": chat_id,
            "message_id": tg_message_id,
            "reply_markup": json.dumps({"inline_keyboard": []}),
        })
        if suffix:
            _telegram("sendMessage", {
                "chat_id": chat_id,
                "text": suffix.strip(),
                "parse_mode": "Markdown",
            })
    except Exception as exc:
        logger.warning(json.dumps({"event": "remove_buttons_failed", "error": str(exc)}))


def _invoke_whatsapp_sender(to: str, message: str, message_id: str) -> None:
    env = os.environ.get("ENV", "dev")
    payload = WhatsAppSenderRequest(
        to_phone_number=to,
        message=message,
        message_id=message_id,
    )
    _get_lambda_client().invoke(
        FunctionName=f"ghost-whatsapp-sender-{env}",
        InvocationType="Event",
        Payload=json.dumps(payload.model_dump()).encode(),
    )


def _esc(text: str) -> str:
    return text.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")
