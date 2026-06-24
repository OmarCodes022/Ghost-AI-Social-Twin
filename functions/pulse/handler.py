import json
import logging
import os
import random
from datetime import datetime, timezone

import boto3

from .conditions import evaluate_condition
from .db import (
    close_conversation,
    fetch_active_defer_conditions,
    fetch_active_intentions,
    fetch_all_contact_states,
    fetch_contact_messages_since,
    fetch_ghost_state,
    fetch_open_conversations,
    fetch_upcoming_life_events,
    mark_condition_resolved,
    update_pulse_score,
)
from .guardrails import is_outreach_allowed
from .scoring import SCORE_THRESHOLD, compute_pulse_score

log = logging.getLogger(__name__)
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_sqs = None

PULSE_QUEUE_URL = os.environ["PULSE_QUEUE_URL"]
HEARTBEAT_QUEUE_URL = os.environ["HEARTBEAT_QUEUE_URL"]
MEMORY_QUEUE_URL = os.environ["MEMORY_QUEUE_URL"]


def _get_sqs():
    global _sqs
    if not _sqs:
        _sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
    return _sqs


def lambda_handler(event, context):
    now = datetime.now(timezone.utc)
    sqs = _get_sqs()

    # Step 1 - global state (read once, shared across all contacts)
    ghost_state = fetch_ghost_state()

    # Step 2 - full read across all contacts
    contacts = fetch_all_contact_states()
    defer_conditions = fetch_active_defer_conditions()
    open_convs = fetch_open_conversations()
    intentions = fetch_active_intentions()
    life_events = fetch_upcoming_life_events()

    # message-based conditions need a count since the oldest active condition
    oldest = min((dc["created_at"] for dc in defer_conditions), default=now)
    messages_since = fetch_contact_messages_since(oldest)

    # index by contact_phone to avoid O(n*m) lookups
    phones = {c["phone"] for c in contacts}

    cond_by_phone = {p: [] for p in phones}
    for dc in defer_conditions:
        if dc["contact_phone"] in cond_by_phone:
            cond_by_phone[dc["contact_phone"]].append(dc)

    conv_by_phone = {p: [] for p in phones}
    for cv in open_convs:
        if cv["contact_phone"] in conv_by_phone:
            conv_by_phone[cv["contact_phone"]].append(cv)

    intent_by_phone = {p: [] for p in phones}
    for it in intentions:
        if it["contact_phone"] in intent_by_phone:
            intent_by_phone[it["contact_phone"]].append(it)

    event_by_phone = {p: [] for p in phones}
    for ev in life_events:
        if ev["contact_phone"] in event_by_phone:
            event_by_phone[ev["contact_phone"]].append(ev)

    for c in contacts:
        p = c["phone"]
        c["defer_conditions"] = cond_by_phone.get(p, [])
        c["open_conversations"] = conv_by_phone.get(p, [])
        c["ghost_intentions"] = intent_by_phone.get(p, [])
        c["life_events"] = event_by_phone.get(p, [])

    flagged = []
    flagged_phones = set()

    for contact in contacts:
        phone = contact["phone"]

        # Step 3 - evaluate active defer conditions
        for dc in contact["defer_conditions"]:
            ctx = {
                "created_at": dc["created_at"],
                "ghost_state": ghost_state,
                "contact": contact,
                "messages_since_condition": messages_since.get(phone, 0),
                "life_events": contact["life_events"],
                "ghost_intentions": contact["ghost_intentions"],
            }
            if evaluate_condition(dc["condition"], ctx, now):
                mark_condition_resolved(dc["id"])
                if phone not in flagged_phones:
                    flagged.append({"phone": phone, "reason": "defer_ready", "condition_id": dc["id"]})
                    flagged_phones.add(phone)

        # Step 3b - evaluate conversation close conditions
        for conv in contact["open_conversations"]:
            cc = conv.get("close_condition")
            if not cc:
                continue
            ctx = {
                "created_at": conv["started_at"],
                "ghost_state": ghost_state,
                "contact": contact,
                "messages_since_condition": messages_since.get(phone, 0),
                "life_events": contact["life_events"],
                "ghost_intentions": contact["ghost_intentions"],
            }
            if evaluate_condition(cc, ctx, now):
                close_conversation(conv["id"])
                sqs.send_message(
                    QueueUrl=MEMORY_QUEUE_URL,
                    MessageBody=json.dumps({
                        "conversation_id": conv["id"],
                        "contact_phone": phone,
                        "trigger": "conversation_closed",
                    }),
                )

        # Step 4 - update continuous weighted pulse_score
        score = compute_pulse_score(contact, ghost_state, now)
        update_pulse_score(phone, score)

        # Step 5 - threshold + hard guardrails
        if phone not in flagged_phones and score >= SCORE_THRESHOLD:
            if is_outreach_allowed(contact, now):
                flagged.append({"phone": phone, "reason": "threshold_crossed"})
                flagged_phones.add(phone)

    # Step 7 - one heartbeat message per flagged contact
    for item in flagged:
        sqs.send_message(
            QueueUrl=HEARTBEAT_QUEUE_URL,
            MessageBody=json.dumps(item),
        )

    log.info("pulse_cycle contacts=%d flagged=%d", len(contacts), len(flagged))

    # Re-enqueue self (self-perpetuating SQS loop, 60-120s)
    sqs.send_message(
        QueueUrl=PULSE_QUEUE_URL,
        MessageBody=json.dumps({"cycle": "pulse"}),
        DelaySeconds=random.randint(60, 120),
    )

    return {"contacts": len(contacts), "flagged": len(flagged)}
