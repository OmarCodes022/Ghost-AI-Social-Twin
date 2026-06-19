import json
import logging
import os
import time

from whatsapp import mark_read, send_text

log = logging.getLogger(__name__)
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

CHARS_PER_SECOND = 12
MIN_DELAY = 1.0
MAX_DELAY = 6.0


def lambda_handler(event, context):
    for record in event["Records"]:
        _send(json.loads(record["body"]))


def _send(payload: dict) -> None:
    to = payload["to_phone_number"]
    content = payload["content"]
    inbound_id = payload.get("inbound_message_id")
    reply_to = payload.get("reply_to_message_id")

    if inbound_id:
        try:
            mark_read(inbound_id)
        except Exception as e:
            log.warning("mark_read failed: %s", e)

    delay = max(MIN_DELAY, min(MAX_DELAY, len(content) / CHARS_PER_SECOND))
    log.info("typing delay %.1fs for %d chars to %s", delay, len(content), to)
    time.sleep(delay)

    result = send_text(to=to, text=content, reply_to=reply_to)
    wamid = (result.get("messages") or [{}])[0].get("id")
    log.info("sent wamid=%s to %s", wamid, to)
