"""ghost_whatsapp_sender

Sends a WhatsApp text message via the Meta Cloud API.

Typing simulation flow per message part:
  1. If part_index > 0: sleep part_index * INTER_MESSAGE_GAP (sequential stagger)
  2. show_typing(inbound_message_id) — triggers the "..." bubble + marks message read
  3. Sleep proportional to message length (clamped 1s–6s)
  4. send_text_message
"""
import json
import logging
import os
import time
from typing import Any

from models import WhatsAppSenderRequest
from whatsapp import send_text_message, show_typing

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

CHARS_PER_SECOND = 15       # realistic casual typing speed
INTER_MESSAGE_GAP = 4       # seconds between sequential parts
MAX_TYPING_DURATION = 6.0
MIN_TYPING_DURATION = 1.0


def lambda_handler(event: dict, context: Any) -> dict:
    logger.info(json.dumps({"event": "whatsapp_sender_invoked"}))

    request = WhatsAppSenderRequest(**event)

    # Stagger sequential parts so they arrive one at a time
    if request.part_index > 0:
        time.sleep(request.part_index * INTER_MESSAGE_GAP)

    # Show typing bubble (also marks the inbound message as read)
    if request.inbound_message_id:
        show_typing(request.inbound_message_id)

    # Sleep proportional to message length
    typing_duration = max(
        MIN_TYPING_DURATION,
        min(MAX_TYPING_DURATION, len(request.message) / CHARS_PER_SECOND),
    )
    time.sleep(typing_duration)

    result = send_text_message(
        to=request.to_phone_number,
        text=request.message,
        context_message_id=request.reply_to_message_id if request.part_index == 0 else None,
    )

    logger.info(json.dumps({
        "event": "message_sent",
        "to": request.to_phone_number,
        "part_index": request.part_index,
        "typing_duration": round(typing_duration, 2),
        "wamid": (result.get("messages") or [{}])[0].get("id"),
    }))

    return {"statusCode": 200, "body": json.dumps(result)}
