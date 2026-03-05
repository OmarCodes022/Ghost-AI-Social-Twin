"""ghost_whatsapp_sender

Sends a WhatsApp text message via the Meta Cloud API.

Accepts a ``WhatsAppSenderRequest`` JSON payload, delegates to the shared
``whatsapp.send_text_message`` helper, and returns the Graph API response.

Can be invoked synchronously (RequestResponse) for immediate confirmation or
asynchronously (Event) by the orchestrator.
"""
import json
import logging
import os
from typing import Any

from models import WhatsAppSenderRequest
from whatsapp import send_text_message

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def lambda_handler(event: dict, context: Any) -> dict:
    logger.info(json.dumps({"event": "whatsapp_sender_invoked"}))

    request = WhatsAppSenderRequest(**event)

    result = send_text_message(to=request.to_phone_number, text=request.message)

    logger.info(
        json.dumps(
            {
                "event": "message_sent",
                "to": request.to_phone_number,
                "wamid": (result.get("messages") or [{}])[0].get("id"),
            }
        )
    )

    return {"statusCode": 200, "body": json.dumps(result)}
