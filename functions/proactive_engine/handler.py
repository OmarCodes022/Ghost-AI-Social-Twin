"""ghost_proactive_engine

Scheduled Lambda (every 2 hours) that decides who Ghost should reach out to
proactively — without waiting for an inbound message.

Two trigger types:
  quiet   — Ghost sent the last message and the contact hasn't replied for 3–24h.
             Ghost follows up naturally, continuing the thread.
  checkin — Ghost hasn't interacted with a tier 1–2 contact in 3–30 days.
             Ghost initiates a fresh, natural check-in.

Routing:
  tier 1–2 → auto-send via whatsapp_sender
  tier 3+  → Telegram approval (reuses existing escalation flow)
"""
import json
import logging
import os
import random
import uuid
from datetime import datetime, timezone
from typing import Any

import anthropic
import boto3

from db import get_cursor
from models import TelegramEscalationEvent, WhatsAppSenderRequest
from ssm import get_parameter

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

MAX_PER_RUN = 3  # Max proactive messages per cron cycle (avoid flooding)

_anthropic_client: anthropic.Anthropic | None = None
_lambda_client: Any = None
_sns_client: Any = None


def _get_anthropic_client(env: str) -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        api_key = get_parameter(f"/ghost/{env}/anthropic/api_key")
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
    return _anthropic_client


def _get_lambda_client():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda")
    return _lambda_client


def _get_sns_client():
    global _sns_client
    if _sns_client is None:
        _sns_client = boto3.client("sns")
    return _sns_client


# ─── Entry point ──────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context: Any) -> dict:
    env = os.environ.get("ENV", "dev")
    logger.info(json.dumps({"event": "proactive_engine_invoked"}))

    candidates = _get_quiet_candidates() + _get_checkin_candidates()

    # Deduplicate by phone number
    seen: set[str] = set()
    unique: list[dict] = []
    for c in candidates:
        if c["phone_number"] not in seen:
            seen.add(c["phone_number"])
            unique.append(c)

    random.shuffle(unique)
    selected = unique[:MAX_PER_RUN]

    logger.info(json.dumps({
        "event": "proactive_candidates_found",
        "total": len(unique),
        "selected": len(selected),
    }))

    for contact in selected:
        try:
            _handle_proactive(contact, env)
        except Exception as exc:
            logger.error(json.dumps({
                "event": "proactive_handle_failed",
                "phone": contact.get("phone_number"),
                "error": str(exc),
            }))

    return {"statusCode": 200, "processed": len(selected)}


# ─── Candidate queries ────────────────────────────────────────────────────────

def _get_quiet_candidates() -> list[dict]:
    """Contacts where Ghost sent the last message and no reply for 3–24h."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT c.phone_number, c.name, c.relationship_tier, c.voice_profile,
                   conv.id AS conversation_id, 'quiet' AS trigger_type
            FROM contacts c
            JOIN conversations conv ON conv.contact_phone = c.phone_number
            WHERE conv.arc_state IN ('open', 'flowing')
              AND c.relationship_tier <= 3
              AND conv.last_message_at BETWEEN NOW() - INTERVAL '24 hours'
                                           AND NOW() - INTERVAL '3 hours'
              AND (
                  SELECT role FROM messages
                  WHERE conversation_id = conv.id
                  ORDER BY sent_at DESC LIMIT 1
              ) = 'agent'
            ORDER BY c.relationship_tier ASC, conv.last_message_at ASC
            """
        )
        return [dict(r) for r in cur.fetchall()]


def _get_checkin_candidates() -> list[dict]:
    """Tier 1–2 contacts with no interaction for 3–30 days and no active convo today."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT c.phone_number, c.name, c.relationship_tier, c.voice_profile,
                   NULL AS conversation_id, 'checkin' AS trigger_type
            FROM contacts c
            WHERE c.relationship_tier <= 2
              AND c.last_interaction BETWEEN NOW() - INTERVAL '30 days'
                                         AND NOW() - INTERVAL '3 days'
              AND NOT EXISTS (
                  SELECT 1 FROM conversations conv
                  WHERE conv.contact_phone = c.phone_number
                    AND conv.arc_state IN ('open', 'flowing')
                    AND conv.last_message_at > NOW() - INTERVAL '24 hours'
              )
            """
        )
        return [dict(r) for r in cur.fetchall()]


# ─── Core logic ───────────────────────────────────────────────────────────────

def _handle_proactive(contact: dict, env: str) -> None:
    phone = contact["phone_number"]
    tier = int(contact.get("relationship_tier") or 3)
    trigger_type = contact["trigger_type"]
    conv_id = contact.get("conversation_id")
    voice_profile = contact.get("voice_profile") or {}

    history = _get_conversation_history(conv_id) if conv_id else []
    persona = voice_profile.get("persona", "default")
    identity_chunks = _get_identity_chunks(persona)
    memory_chunks = _get_memory_chunks(phone)

    message_text = _generate_proactive_message(
        contact=contact,
        history=history,
        identity_chunks=identity_chunks,
        memory_chunks=memory_chunks,
        trigger_type=trigger_type,
        env=env,
    )

    if not message_text or message_text.strip().lower().startswith("[skip]"):
        logger.info(json.dumps({
            "event": "proactive_skipped",
            "phone": phone,
            "trigger": trigger_type,
        }))
        return

    # Ensure there's an active conversation to attach the message to
    if not conv_id:
        conv_id = _get_or_create_conversation(phone)

    msg_id = _log_proactive_message(conv_id, message_text)

    if tier <= 2:
        # Auto-send
        parts = [p.strip() for p in message_text.split("\n") if p.strip()]
        for i, part in enumerate(parts):
            _invoke_whatsapp_sender(env, phone, part, msg_id if i == 0 else None, i)
        logger.info(json.dumps({
            "event": "proactive_sent",
            "phone": phone,
            "trigger": trigger_type,
            "parts": len(parts),
        }))
    else:
        # Telegram approval
        _publish_for_approval(env, contact, message_text, msg_id, trigger_type)
        logger.info(json.dumps({
            "event": "proactive_escalated",
            "phone": phone,
            "trigger": trigger_type,
        }))


# ─── Claude call ──────────────────────────────────────────────────────────────

def _generate_proactive_message(
    contact: dict,
    history: list[dict],
    identity_chunks: list[str],
    memory_chunks: list[dict],
    trigger_type: str,
    env: str,
) -> str:
    voice_profile = contact.get("voice_profile") or {}
    persona_name = voice_profile.get("persona_name", "Omar")
    contact_name = contact.get("name") or contact["phone_number"]
    preferred_lang = voice_profile.get("preferred_language")

    lang_rule = (
        f"Write in {preferred_lang}."
        if preferred_lang
        else "Write in the same language as the conversation history, or French if no history."
    )

    if trigger_type == "quiet":
        trigger_instruction = (
            f"You sent the last message and {contact_name} hasn't replied for a while. "
            "Send a natural, low-pressure follow-up. Don't reference the wait or the silence. "
            "Just something casual — a thought, continue the thread, or a light question. "
            "If the conversation had no real energy left and a follow-up would feel forced, "
            "reply with exactly: [skip]"
        )
    else:  # checkin
        trigger_instruction = (
            f"You haven't spoken to {contact_name} in a while. "
            "Reach out naturally — reference something you know about them, "
            "share something you thought of, or just send a genuine check-in. "
            "Keep it real and casual. Don't be dramatic about the silence. "
            "If there's genuinely nothing natural to say, reply with exactly: [skip]"
        )

    system_lines = [
        f"You are Ghost — an AI standing in for {persona_name} in private WhatsApp conversations.",
        f"Respond exactly as {persona_name} would. Never reveal you are an AI.",
        f"LANGUAGE: {lang_rule}",
        f"Apply {persona_name}'s casual style (short, lowercase, minimal punctuation, slang) in whatever language you use.",
        "",
        f"## Your task",
        trigger_instruction,
        "",
        "## Formatting rules",
        "- Split into short natural messages using a newline between each part.",
        "- Each line = one WhatsApp message. Keep each line very short.",
        "- Lowercase only. Minimal punctuation. No emojis unless sparingly used.",
        "- Output ONLY the message text or [skip]. No preamble, labels, or quotes.",
        "",
    ]

    if identity_chunks:
        system_lines.append(f"## {persona_name}'s personality and style")
        for chunk in identity_chunks:
            system_lines.append(chunk)
        system_lines.append("")

    if memory_chunks:
        system_lines.append(f"## What you know about {contact_name}")
        for chunk in memory_chunks:
            content = chunk.get("content", "")
            if content:
                system_lines.append(f"- {content}")
        system_lines.append("")

    if voice_profile:
        system_lines.append(f"## {contact_name}'s communication style")
        for k, v in voice_profile.items():
            system_lines.append(f"- {k}: {v}")
        system_lines.append("")

    system_prompt = "\n".join(system_lines)

    # Build messages from history (oldest-first, Claude format)
    messages: list[dict] = []
    for row in history:
        role = "assistant" if row["role"] == "agent" else "user"
        messages.append({"role": role, "content": row["content"]})

    # Strip leading assistant turns (Claude requires user first)
    while messages and messages[0]["role"] == "assistant":
        messages.pop(0)

    # For checkin with no history, seed with a user message so Claude has context
    if not messages:
        messages = [{"role": "user", "content": f"[{contact_name} is waiting for you to reach out]"}]

    # Ensure last role is "user" so Claude generates the next assistant turn
    if messages[-1]["role"] == "assistant":
        messages.append({"role": "user", "content": "[continue the conversation — it's your turn to reach out]"})

    client = _get_anthropic_client(env)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        system=system_prompt,
        messages=messages,
    )

    reply = response.content[0].text.strip()

    logger.info(json.dumps({
        "event": "proactive_message_generated",
        "phone": contact["phone_number"],
        "trigger": trigger_type,
        "reply_length": len(reply),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }))

    return reply


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _get_identity_chunks(persona: str = "default") -> list[str]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT content FROM knowledge_chunks
            WHERE contact_phone IS NULL AND category = 'identity' AND persona = %s
            ORDER BY created_at ASC
            """,
            (persona,),
        )
        return [row["content"] for row in cur.fetchall()]


def _get_conversation_history(conversation_id: str, limit: int = 15) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT role, content
            FROM (
                SELECT role, content, sent_at
                FROM messages
                WHERE conversation_id = %s
                ORDER BY sent_at DESC
                LIMIT %s
            ) sub
            ORDER BY sent_at ASC
            """,
            (conversation_id, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def _get_memory_chunks(contact_phone: str, limit: int = 5) -> list[dict]:
    """Best-effort full-text search over contact's knowledge chunks."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT content, category
            FROM knowledge_chunks
            WHERE contact_phone = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (contact_phone, limit),
        )
        return [dict(row) for row in cur.fetchall()]


def _get_or_create_conversation(phone: str) -> str:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id FROM conversations
            WHERE contact_phone = %s AND arc_state IN ('open', 'flowing')
            ORDER BY last_message_at DESC LIMIT 1
            """,
            (phone,),
        )
        row = cur.fetchone()
        if row:
            return str(row["id"])

        conv_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO conversations
                (id, contact_phone, arc_state, started_at, last_message_at, message_count)
            VALUES (%s, %s, 'open', NOW(), NOW(), 1)
            """,
            (conv_id, phone),
        )
        return conv_id


def _log_proactive_message(conversation_id: str, content: str) -> str:
    msg_id = str(uuid.uuid4())
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO messages
                (id, conversation_id, role, content, sent_at,
                 was_delayed, delay_seconds, confidence_score, escalated)
            VALUES (%s, %s, 'agent', %s, NOW(), false, 0, 1.0, false)
            """,
            (msg_id, conversation_id, content),
        )
        # Update conversation timestamp
        cur.execute(
            "UPDATE conversations SET last_message_at = NOW() WHERE id = %s",
            (conversation_id,),
        )
    return msg_id


# ─── Downstream invocations ───────────────────────────────────────────────────

def _invoke_whatsapp_sender(
    env: str,
    to_phone_number: str,
    message: str,
    message_id: str | None,
    part_index: int = 0,
) -> None:
    request = WhatsAppSenderRequest(
        to_phone_number=to_phone_number,
        message=message,
        message_id=message_id,
        part_index=part_index,
    )
    _get_lambda_client().invoke(
        FunctionName=f"ghost-whatsapp-sender-{env}",
        InvocationType="Event",
        Payload=json.dumps(request.model_dump()).encode(),
    )


def _publish_for_approval(
    env: str,
    contact: dict,
    message_text: str,
    message_id: str,
    trigger_type: str,
) -> None:
    topic_arn = os.environ.get("ESCALATIONS_TOPIC_ARN", "")
    escalation_id = str(uuid.uuid4())

    reason = (
        "Ghost wants to follow up — contact hasn't replied to your last message."
        if trigger_type == "quiet"
        else "Ghost wants to check in — you haven't talked to this contact in a while."
    )

    payload = TelegramEscalationEvent(
        escalation_id=escalation_id,
        message_id=message_id,
        contact_phone=contact["phone_number"],
        contact_name=contact.get("name"),
        original_message=f"[proactive / {trigger_type}]",
        proposed_reply=message_text,
        reason=reason,
        confidence=1.0,
    )

    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO escalations (id, message_id, reason, confidence) VALUES (%s, %s, %s, %s)",
            (escalation_id, message_id, reason, 1.0),
        )

    _get_sns_client().publish(
        TopicArn=topic_arn,
        Message=payload.model_dump_json(),
    )
