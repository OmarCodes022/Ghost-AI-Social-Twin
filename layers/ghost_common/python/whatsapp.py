"""WhatsApp Meta Cloud API client.

Credentials are fetched from SSM on first use and cached in-process.
All public functions raise on HTTP errors — callers are responsible for
structured logging and re-raising.
"""
import logging
from typing import Any

import requests

from ssm import get_parameter

logger = logging.getLogger(__name__)

_GRAPH_API_VERSION = "v19.0"
_GRAPH_BASE = f"https://graph.facebook.com/{_GRAPH_API_VERSION}"

# Module-level cache so warm Lambda invocations skip SSM lookups.
_token: str | None = None
_phone_number_id: str | None = None


def _get_token() -> str:
    global _token
    if _token is None:
        _token = get_parameter("/ghost/whatsapp/token")
    return _token


def _get_phone_number_id() -> str:
    global _phone_number_id
    if _phone_number_id is None:
        _phone_number_id = get_parameter("/ghost/whatsapp/phone_number_id")
    return _phone_number_id


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_get_token()}",
        "Content-Type": "application/json",
    }


def send_text_message(to: str, text: str, context_message_id: str | None = None) -> dict[str, Any]:
    """Send a plain-text WhatsApp message.

    Args:
        to: Recipient E.164 phone number (e.g. ``447700900000``).
        text: Message body (up to 4096 characters).
        context_message_id: Optional wamid to quote — shows a reply bubble above the message.

    Returns:
        Parsed JSON response from the Meta Graph API.

    Raises:
        requests.HTTPError: On non-2xx responses.
    """
    phone_number_id = _get_phone_number_id()
    url = f"{_GRAPH_BASE}/{phone_number_id}/messages"

    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    if context_message_id:
        payload["context"] = {"message_id": context_message_id}

    response = requests.post(url, json=payload, headers=_headers(), timeout=10)
    response.raise_for_status()

    result: dict[str, Any] = response.json()
    logger.info(
        "WhatsApp message sent",
        extra={"to": to, "wamid": result.get("messages", [{}])[0].get("id")},
    )
    return result


def show_typing(inbound_message_id: str) -> None:
    """Trigger the WhatsApp typing indicator bubble. Best-effort — never raises.

    Also marks the inbound message as read (required by the API to show typing).
    """
    try:
        phone_number_id = _get_phone_number_id()
        url = f"{_GRAPH_BASE}/{phone_number_id}/messages"
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": inbound_message_id,
            "typing_indicator": {"type": "text"},
        }
        requests.post(url, json=payload, headers=_headers(), timeout=5)
    except Exception:
        pass  # typing indicator is cosmetic, never block on it


def mark_message_read(message_id: str) -> dict[str, Any]:
    """Mark an inbound message as read (sends read receipt).

    Args:
        message_id: The ``id`` field from the inbound webhook payload.

    Returns:
        Parsed JSON response from the Meta Graph API.
    """
    phone_number_id = _get_phone_number_id()
    url = f"{_GRAPH_BASE}/{phone_number_id}/messages"

    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }

    response = requests.post(url, json=payload, headers=_headers(), timeout=10)
    response.raise_for_status()
    return response.json()
