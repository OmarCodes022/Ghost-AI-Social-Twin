import os
import requests
from ssm import get_parameter

_BASE = "https://graph.facebook.com/v19.0"


def _token() -> str:
    return get_parameter(f"/ghost/{os.environ['ENV']}/whatsapp/token")


def _phone_id() -> str:
    return get_parameter(f"/ghost/{os.environ['ENV']}/whatsapp/phone_number_id")


def _headers() -> dict:
    return {"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"}


def mark_read(message_id: str) -> None:
    requests.post(
        f"{_BASE}/{_phone_id()}/messages",
        headers=_headers(),
        json={"messaging_product": "whatsapp", "status": "read", "message_id": message_id},
        timeout=10,
    ).raise_for_status()


def set_typing(to: str) -> None:
    try:
        requests.post(
            f"{_BASE}/{_phone_id()}/messages",
            headers=_headers(),
            json={"messaging_product": "whatsapp", "to": to, "status": "typing"},
            timeout=5,
        )
    except Exception:
        pass


def send_text(to: str, text: str, reply_to: str | None = None) -> dict:
    body = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": text, "preview_url": False},
    }
    if reply_to:
        body["context"] = {"message_id": reply_to}

    resp = requests.post(
        f"{_BASE}/{_phone_id()}/messages",
        headers=_headers(),
        json=body,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()
