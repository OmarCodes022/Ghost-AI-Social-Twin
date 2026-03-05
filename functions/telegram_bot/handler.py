"""ghost_telegram_bot

Receives SNS escalation events and forwards them to a Telegram chat as a
formatted message with three inline action buttons:

  ✅ Send   — approve the proposed reply as-is
  ✏️ Edit   — signal that the human wants to edit before sending
  ⏭️ Skip   — discard the reply entirely

Callback query handling (button press) is a separate concern — Telegram will
POST to a webhook URL. For now, this Lambda only *sends* notifications; the
callback handler is Phase 2.
"""
import json
import logging
import os
from typing import Any

import requests

from models import TelegramEscalationEvent
from ssm import get_parameter

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"

_bot_token: str | None = None
_chat_id: str | None = None


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


# ─── Entry point ──────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context: Any) -> dict:
    logger.info(json.dumps({"event": "telegram_bot_invoked"}))

    records = event.get("Records", [])
    for record in records:
        sns = record.get("Sns", {})
        message_str = sns.get("Message", "{}")

        try:
            message_body = json.loads(message_str)
            escalation = TelegramEscalationEvent(**message_body)
            _send_escalation_notification(escalation)
        except Exception as exc:
            logger.error(
                json.dumps(
                    {
                        "event": "escalation_processing_failed",
                        "error": str(exc),
                        "sns_message_id": sns.get("MessageId"),
                    }
                )
            )
            raise

    return {"statusCode": 200}


# ─── Telegram notification ─────────────────────────────────────────────────────

def _send_escalation_notification(escalation: TelegramEscalationEvent) -> None:
    token = _get_bot_token()
    chat_id = _get_chat_id()

    contact_display = escalation.contact_name or escalation.contact_phone
    confidence_pct = f"{escalation.confidence:.0%}"

    text = (
        f"*Ghost Escalation*\n\n"
        f"*From:* {contact_display}\n"
        f"*Their message:*\n_{_escape_md(escalation.original_message)}_\n\n"
        f"*Proposed reply:*\n_{_escape_md(escalation.proposed_reply)}_\n\n"
        f"*Reason:* {escalation.reason}\n"
        f"*Confidence:* {confidence_pct}"
    )

    inline_keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "Send",
                    "callback_data": f"send:{escalation.escalation_id}",
                },
                {
                    "text": "Edit",
                    "callback_data": f"edit:{escalation.escalation_id}",
                },
                {
                    "text": "Skip",
                    "callback_data": f"skip:{escalation.escalation_id}",
                },
            ]
        ]
    }

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(inline_keyboard),
    }

    response = requests.post(url, json=payload, timeout=10)
    response.raise_for_status()

    result = response.json()
    telegram_message_id = str(
        result.get("result", {}).get("message_id", "")
    )

    logger.info(
        json.dumps(
            {
                "event": "telegram_notification_sent",
                "escalation_id": escalation.escalation_id,
                "telegram_message_id": telegram_message_id,
            }
        )
    )


def _escape_md(text: str) -> str:
    """Minimal escaping for Telegram Markdown v1 inside italic blocks."""
    return text.replace("_", "\\_").replace("*", "\\*").replace("`", "\\`")
