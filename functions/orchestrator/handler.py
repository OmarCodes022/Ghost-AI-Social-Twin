"""ghost_orchestrator — entry point.

Receives an inbound WhatsApp message (direct invoke or SQS delayed re-invoke),
runs the Claude agent loop, and routes the result to WhatsApp / Telegram / SQS.
"""
import json
import logging
import os
from typing import Any

from agent import run_agent_loop
from db_helpers import (
    acquire_reply_lock,
    already_processed,
    get_burst_messages,
    get_ghost_state,
    get_identity_chunks,
    is_superseded,
    load_or_create_contact,
    load_or_create_conversation,
    log_message,
    save_agent_trace,
)
from debug import send_dev_debug
from dispatch import enqueue_delay, invoke_whatsapp_sender
from models import MessageRole, OrchestratorEvent

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


# ─── Entry point ──────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context: Any) -> None:
    if "Records" in event:
        for record in event["Records"]:
            _process(OrchestratorEvent(**json.loads(record["body"])))
        return
    _process(OrchestratorEvent(**event))


# ─── Core pipeline ────────────────────────────────────────────────────────────

_BLOCKED = {"201222540825"}


def _process(orch_event: OrchestratorEvent) -> None:
    logger.info(json.dumps({"event": "orchestrator_invoked", "is_delayed": orch_event.is_delayed}))

    inbound = orch_event.inbound_message
    env = os.environ.get("ENV", "dev")
    is_dev = env == "dev"

    if inbound.phone_number in _BLOCKED:
        logger.info(json.dumps({"event": "blocked_number_skipped", "phone": inbound.phone_number}))
        return

    if already_processed(inbound.message_id):
        logger.info(json.dumps({"event": "duplicate_message_skipped", "wamid": inbound.message_id}))
        return

    contact = load_or_create_contact(inbound.phone_number)
    conversation = load_or_create_conversation(inbound.phone_number)

    msg = log_message(
        conversation_id=conversation.id,
        role=MessageRole.user,
        content=inbound.content,
        whatsapp_message_id=inbound.message_id,
    )

    logger.info(json.dumps({
        "event": "inbound_message_logged",
        "phone": inbound.phone_number,
        "conversation_id": conversation.id,
    }))

    burst = get_burst_messages(conversation.id)
    last_wamid = burst[-1].get("whatsapp_message_id") if len(burst) > 1 else None

    if is_superseded(conversation.id, msg.id):
        logger.info(json.dumps({"event": "orchestrator_superseded", "conversation_id": conversation.id}))
        return

    identity_chunks = get_identity_chunks(contact.voice_profile)
    ghost_state = get_ghost_state()

    result = run_agent_loop(
        contact=contact,
        conversation=conversation,
        burst=burst,
        identity_chunks=identity_chunks,
        ghost_state=ghost_state,
        is_delayed=orch_event.is_delayed,
    )

    # ── Delay ─────────────────────────────────────────────────────────────────
    if result["action"] == "delay":
        if is_dev:
            logger.info(json.dumps({"event": "dev_delay_skipped", "would_have_delayed": result["seconds"]}))
            # fall through and send immediately in dev
        else:
            save_agent_trace(None, conversation.id, inbound.phone_number, result)
            enqueue_delay(orch_event, result["seconds"], result["reason"])
            return

    # ── Escalate ──────────────────────────────────────────────────────────────
    if result["action"] == "escalate":
        # Escalation disabled — treat draft_reply as a normal reply
        result = {**result, "action": "reply", "reply": result.get("draft_reply", "")}

    # ── Reply ─────────────────────────────────────────────────────────────────
    reply = result.get("reply", "")
    if not reply:
        logger.warning(json.dumps({"event": "empty_reply", "conversation_id": conversation.id}))
        return

    agent_msg = log_message(conversation.id, MessageRole.agent, reply)
    save_agent_trace(agent_msg.id, conversation.id, inbound.phone_number, result)

    if not acquire_reply_lock(conversation.id):
        logger.info(json.dumps({"event": "reply_lock_failed", "conversation_id": conversation.id}))
        return

    parts = [p for p in reply.split("\n") if p.strip()]
    for i, part in enumerate(parts):
        invoke_whatsapp_sender(
            env=env,
            to_phone_number=inbound.phone_number,
            message=part.strip(),
            message_id=agent_msg.id if i == 0 else None,
            part_index=i,
            inbound_message_id=inbound.message_id,
            reply_to_message_id=last_wamid if i == 0 else None,
        )

    if is_dev:
        send_dev_debug(env, contact, inbound.content, ghost_state, result, burst, escalated=False)
