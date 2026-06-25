import json
import logging
import os

import boto3

from channel import Command
from telegram import TelegramChannel

log = logging.getLogger(__name__)
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Swap this line to switch notification platform
_channel = TelegramChannel()

_sqs = None


def _get_sqs():
    global _sqs
    if not _sqs:
        _sqs = boto3.client("sqs", region_name=os.environ["AWS_REGION"])
    return _sqs


def lambda_handler(event, context):
    if "Records" in event:
        for record in event["Records"]:
            _handle_escalation(json.loads(record["body"]))
        return {"statusCode": 200}

    if "body" in event:
        cmd = _channel.parse_command(event)
        if cmd:
            _execute(cmd)
        return _channel.ack(event)

    return {"statusCode": 400, "body": "Unknown event type"}


def _handle_escalation(payload: dict) -> None:
    phone = payload.get("contact_phone", "")
    name = payload.get("contact_name", phone)
    msg = payload.get("content", "")
    reason = payload.get("reason", "")
    try:
        from db import write_escalation
        write_escalation(phone, name, msg, reason)
    except Exception as exc:
        log.warning("failed to write escalation to DB: %s", exc)
    _channel.send_escalation(
        contact_name=name,
        contact_phone=phone,
        message=msg,
        reason=reason,
    )
    log.info("escalation sent for %s", phone)


def _execute(cmd: Command) -> None:
    log.info("command received: type=%s phone=%s", cmd.type, cmd.contact_phone)

    if cmd.type == "status":
        _cmd_status()
    elif cmd.type == "pause" and cmd.contact_phone:
        _cmd_pause(cmd.contact_phone)
    elif cmd.type == "resume" and cmd.contact_phone:
        _cmd_resume(cmd.contact_phone)
    elif cmd.type == "override" and cmd.contact_phone and cmd.args.get("message"):
        _cmd_override(cmd.contact_phone, cmd.args["message"])
    else:
        _channel.send_alert(f"Unknown or incomplete command: `{cmd.type}`")


def _cmd_status() -> None:
    import psycopg2, psycopg2.extras
    from ssm import get_parameter
    url = get_parameter(f"/ghost/{os.environ['ENV']}/db/connection_string")
    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT mood, social_battery, emotional_load, whats_on_mind FROM ghost_state WHERE id = 1"
        )
        row = cur.fetchone()
    conn.close()
    _channel.send_alert(
        f"*Ghost Status*\n"
        f"Mood: {row['mood'] or 'none'}\n"
        f"Social battery: {row['social_battery']:.1f}\n"
        f"Emotional load: {row['emotional_load']:.1f}\n"
        f"On mind: {row['whats_on_mind'] or 'nothing'}"
    )


def _cmd_pause(phone: str) -> None:
    _set_contact_paused(phone, True)
    _channel.send_alert(f"Ghost paused for `{phone}`.")


def _cmd_resume(phone: str) -> None:
    _set_contact_paused(phone, False)
    _channel.send_alert(f"Ghost resumed for `{phone}`.")


def _cmd_override(phone: str, message: str) -> None:
    payload = json.dumps({
        "to_phone_number": phone,
        "content": message,
        "inbound_message_id": None,
        "reply_to_message_id": None,
    })
    _get_sqs().send_message(
        QueueUrl=os.environ["OUTBOUND_QUEUE_URL"],
        MessageBody=payload,
        MessageGroupId=phone,
        MessageDeduplicationId=f"override-{phone}-{hash(message)}",
    )
    _channel.send_alert(f"Override sent to `{phone}`.")


def _set_contact_paused(phone: str, paused: bool) -> None:
    import psycopg2
    from ssm import get_parameter
    url = get_parameter(f"/ghost/{os.environ['ENV']}/db/connection_string")
    conn = psycopg2.connect(url)
    with conn.cursor() as cur:
        # Use pulse_score = -99 as a sentinel for "paused by Omar"
        cur.execute(
            "UPDATE contact_state SET pulse_score = %s, updated_at = NOW() WHERE contact_phone = %s",
            (-99.0 if paused else 0.0, phone),
        )
    conn.commit()
    conn.close()
