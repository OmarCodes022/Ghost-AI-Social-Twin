import os
import re
import requests
from typing import Optional

from channel import Command, NotificationChannel
from ssm import get_parameter

_BASE = "https://api.telegram.org/bot{token}"

_COMMANDS = {"pause", "resume", "status", "override"}


class TelegramChannel(NotificationChannel):
    def _token(self) -> str:
        return get_parameter(f"/ghost/{os.environ['ENV']}/telegram/bot_token")

    def _chat_id(self) -> str:
        return get_parameter(f"/ghost/{os.environ['ENV']}/telegram/chat_id")

    def _post(self, method: str, **kwargs) -> dict:
        url = _BASE.format(token=self._token()) + f"/{method}"
        resp = requests.post(url, json=kwargs, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def send_alert(self, text: str) -> None:
        self._post("sendMessage", chat_id=self._chat_id(), text=text, parse_mode="Markdown")

    def send_escalation(
        self,
        contact_name: str,
        contact_phone: str,
        message: str,
        reason: str,
    ) -> None:
        text = (
            f"*Escalation* from {contact_name} (`{contact_phone}`)\n\n"
            f"*Message:* {message}\n\n"
            f"*Reason:* {reason}\n\n"
            f"Reply `/override {contact_phone} <your message>` to respond manually."
        )
        self.send_alert(text)

    def parse_command(self, webhook_event: dict) -> Optional[Command]:
        body = webhook_event.get("body")
        if not body:
            return None

        import json
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            return None

        text = (
            data.get("message", {}).get("text", "")
            or data.get("edited_message", {}).get("text", "")
        ).strip()

        if not text.startswith("/"):
            return None

        parts = text.lstrip("/").split(maxsplit=2)
        cmd_name = parts[0].lower()
        if cmd_name not in _COMMANDS:
            return None

        phone = parts[1] if len(parts) > 1 and re.match(r"^\+?\d+$", parts[1]) else None
        extra = parts[-1] if len(parts) > (2 if phone else 1) else None

        return Command(
            type=cmd_name,
            contact_phone=phone,
            args={"message": extra} if extra else {},
        )

    def ack(self, webhook_event: dict) -> dict:
        return {"statusCode": 200, "body": "OK"}
