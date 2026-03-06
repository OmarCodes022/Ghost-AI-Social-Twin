"""ghost_response_generator

Drafts a reply using the identity profile, contact voice calibration, current
mood vector, and memory chunks retrieved from pgvector.
Calls Claude (claude-sonnet-4-20250514) with a rich system prompt.

Reply format: Claude outputs one or more short messages separated by newlines.
The orchestrator splits on "\n" and sends each part as a separate WhatsApp message.
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
    identity_chunks = _get_identity_chunks()

    system_prompt = _build_system_prompt(
        mood_state=request.mood_state,
        memory_chunks=request.memory_chunks,
        identity_chunks=identity_chunks,
        voice_profile=request.voice_profile,
    )
    messages = _build_messages(history, request.inbound_message)

    client = _get_anthropic_client()
    claude_resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=300,
        system=system_prompt,
        messages=messages,
    )

    reply = claude_resp.content[0].text.strip()

    logger.info(json.dumps({
        "event": "response_generated",
        "contact_phone": request.contact_phone,
        "conversation_id": request.conversation_id,
        "reply_length": len(reply),
        "input_tokens": claude_resp.usage.input_tokens,
        "output_tokens": claude_resp.usage.output_tokens,
    }))

    return ResponseGeneratorResponse(
        reply=reply,
        confidence_score=1.0,
    ).model_dump(mode="json")


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _get_identity_chunks() -> list[str]:
    """Always fetch all identity knowledge chunks regardless of query match."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT content FROM knowledge_chunks
            WHERE contact_phone IS NULL AND category = 'identity'
            ORDER BY created_at ASC
            """
        )
        return [row["content"] for row in cur.fetchall()]


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


# ─── Prompt builder ───────────────────────────────────────────────────────────

def _build_system_prompt(
    mood_state: MoodState,
    memory_chunks: list[dict],
    identity_chunks: list[str],
    voice_profile: dict | None,
) -> str:
    lines = [
        "You are Ghost — an AI standing in for Omar in private WhatsApp conversations.",
        "Respond exactly as Omar would. Never reveal you are an AI.",
        "",
    ]

    # Identity — always included, anchors the whole prompt
    if identity_chunks:
        lines.append("## Omar's personality and style")
        for chunk in identity_chunks:
            lines.append(chunk)
        lines.append("")

    # Hard formatting rules
    lines += [
        "## Formatting rules (non-negotiable)",
        "- Split your reply into short natural messages using a newline between each part.",
        "  Example output for a casual check-in: yo\\nu around",
        "  Example output for a venting response: damn\\nwhat happened",
        "- Each line = one WhatsApp message send. Keep each line very short.",
        "- Lowercase only. Minimal punctuation. No emojis unless 🍆 or 🫢, and almost never.",
        "- Output ONLY the message text. No preamble, labels, or quotes.",
        "",
    ]

    # Mood — only surface notable states
    mood_notes = []
    if mood_state.energy < 0.3:
        mood_notes.append("low energy right now — keep it brief, slower replies")
    elif mood_state.energy > 0.75:
        mood_notes.append("energised and engaged")
    if mood_state.patience < 0.35:
        mood_notes.append("low patience — be more blunt and direct")
    if mood_state.humor_threshold > 0.7:
        mood_notes.append("in a playful mood")
    if mood_notes:
        lines.append("## Current mood")
        for note in mood_notes:
            lines.append(f"- {note}")
        lines.append("")

    # Contact voice profile (learned from their chat history)
    if voice_profile:
        lines.append("## Contact's communication style")
        for k, v in voice_profile.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

    # Contact-specific memories
    if memory_chunks:
        lines.append("## What you know about this contact")
        for chunk in memory_chunks:
            content = chunk.get("content", "")
            if content:
                lines.append(f"- {content}")
        lines.append("")

    lines.append(
        "Reply ONLY with the message text. Use newlines to split into short natural messages."
    )
    return "\n".join(lines)


def _build_messages(history: list[dict], inbound_message: str) -> list[dict]:
    """Convert DB history rows into Claude messages format.

    History already includes the current inbound message (logged by orchestrator).
    Maps DB role 'agent' → 'assistant', 'user' → 'user'.
    """
    messages = []
    for row in history:
        role = "assistant" if row["role"] == "agent" else "user"
        messages.append({"role": role, "content": row["content"]})

    # Claude requires conversation to start with a user message
    while messages and messages[0]["role"] == "assistant":
        messages.pop(0)

    if not messages:
        messages = [{"role": "user", "content": inbound_message}]

    return messages
