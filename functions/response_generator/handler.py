"""ghost_response_generator

Drafts a reply using the identity profile, contact voice calibration, current
mood vector, and memory chunks retrieved from pgvector.
Calls Claude (claude-sonnet-4-20250514) with a rich system prompt.
"""
import json
import logging
import os
from typing import Any

import anthropic

from db import get_cursor
from models import MoodState, ResponseGeneratorRequest, ResponseGeneratorResponse
from ssm import get_parameter

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_anthropic_client: anthropic.Anthropic | None = None


def _get_anthropic_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        env = os.environ.get("ENV", "dev")
        api_key = get_parameter(f"/ghost/{env}/anthropic/api_key")
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
    return _anthropic_client


# ─── Entry point ──────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context: Any) -> dict:
    logger.info(json.dumps({"event": "response_generator_invoked"}))

    request = ResponseGeneratorRequest(**event)

    history = _get_conversation_history(request.conversation_id)
    system_prompt = _build_system_prompt(
        mood_state=request.mood_state,
        memory_chunks=request.memory_chunks,
        voice_profile=request.voice_profile,
    )
    messages = _build_messages(history, request.inbound_message)

    client = _get_anthropic_client()
    claude_resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        system=system_prompt,
        messages=messages,
    )

    reply = claude_resp.content[0].text.strip()

    logger.info(
        json.dumps({
            "event": "response_generated",
            "contact_phone": request.contact_phone,
            "conversation_id": request.conversation_id,
            "reply_length": len(reply),
            "input_tokens": claude_resp.usage.input_tokens,
            "output_tokens": claude_resp.usage.output_tokens,
        })
    )

    return ResponseGeneratorResponse(
        reply=reply,
        confidence_score=1.0,
    ).model_dump(mode="json")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_conversation_history(conversation_id: str, limit: int = 20) -> list[dict]:
    """Return the last `limit` messages ordered oldest-first."""
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


def _build_system_prompt(
    mood_state: MoodState,
    memory_chunks: list[dict],
    voice_profile: dict | None,
) -> str:
    lines = [
        "You are a social twin — an AI acting as a specific person in a private WhatsApp conversation.",
        "Reply naturally and authentically in that person's voice.",
        "",
        "## Core rules",
        "- Keep replies concise and conversational, like a real WhatsApp message.",
        "- Never reveal you are an AI.",
        "- Match the language, tone, and style of the conversation.",
        "- Avoid unnecessary punctuation, emojis, or formal language unless it fits the voice profile.",
        "",
    ]

    if voice_profile:
        lines.append("## Voice profile")
        for k, v in voice_profile.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

    lines += [
        "## Current mood",
        f"- Energy: {mood_state.energy:.1f}  (0=exhausted → 1=energised)",
        f"- Warmth: {mood_state.warmth:.1f}  (0=cold → 1=warm)",
        f"- Humor: {mood_state.humor_threshold:.1f}  (0=serious → 1=playful)",
        f"- Openness: {mood_state.openness:.1f}",
        f"- Patience: {mood_state.patience:.1f}",
        "",
    ]

    if memory_chunks:
        lines.append("## Relevant memories about this contact")
        for chunk in memory_chunks:
            content = chunk.get("content", "")
            if content:
                lines.append(f"- {content}")
        lines.append("")

    lines.append(
        "Reply ONLY with the message text — no preamble, no commentary, no quotes."
    )
    return "\n".join(lines)


def _build_messages(history: list[dict], inbound_message: str) -> list[dict]:
    """Convert DB history rows into Claude messages format.

    The history already includes the current inbound message (logged by the
    orchestrator before calling us), so we don't append it again.
    Maps DB role 'agent' → 'assistant', 'user' → 'user'.
    Ensures the list starts with a user message.
    """
    messages = []
    for row in history:
        role = "assistant" if row["role"] == "agent" else "user"
        messages.append({"role": role, "content": row["content"]})

    # Drop leading assistant messages (Claude requires user first)
    while messages and messages[0]["role"] == "assistant":
        messages.pop(0)

    # Fallback: if history is empty or something went wrong
    if not messages:
        messages = [{"role": "user", "content": inbound_message}]

    return messages
