"""Strands-based agent loop with RAG pre-fetch and multilingual embeddings."""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Literal

import boto3
from strands import Agent, tool
from strands.models.anthropic import AnthropicModel

from db import get_cursor
from db_helpers import get_identity_chunks, rag_search
from models import Contact, Conversation, GhostState
from ssm import get_parameter
from tools import (
    tool_get_contact_profile,
    tool_get_history,
    tool_get_mood_state,
    tool_save_memory,
    tool_update_contact_profile,
    tool_update_conversation_arc,
    tool_update_mood,
)

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 1024
_RAG_K = 5

# ─── Per-invocation context (safe: Lambda is single-threaded per execution) ───

_ctx_contact: Contact | None = None
_ctx_conversation: Conversation | None = None
_ctx_tool_calls: list[dict] = []
_ctx_terminal: dict = {}

# ─── Cached clients ───────────────────────────────────────────────────────────

_bedrock_client = None
_anthropic_model: AnthropicModel | None = None


def _get_bedrock_client():
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=os.environ.get("AWS_REGION", "eu-west-1"),
        )
    return _bedrock_client


def _get_anthropic_model() -> AnthropicModel:
    global _anthropic_model
    if _anthropic_model is None:
        env = os.environ.get("ENV", "dev")
        api_key = get_parameter(f"/ghost/{env}/anthropic/api_key")
        _anthropic_model = AnthropicModel(
            client_args={"api_key": api_key},
            model_id=_MODEL,
            max_tokens=_MAX_TOKENS,
        )
    return _anthropic_model


# ─── Embedding ────────────────────────────────────────────────────────────────

def embed(text: str) -> list[float] | None:
    """Generate multilingual embedding. Primary: Titan v2 (1536d). Fallback: Voyage."""
    try:
        resp = _get_bedrock_client().invoke_model(
            modelId="amazon.titan-embed-text-v2:0",
            body=json.dumps({"inputText": text[:8192]}),
            contentType="application/json",
            accept="application/json",
        )
        return json.loads(resp["body"].read())["embedding"]
    except Exception as exc:
        if "AccessDenied" in type(exc).__name__ or "AccessDenied" in str(exc):
            logger.warning(json.dumps({"event": "titan_access_denied", "fallback": "voyage"}))
            return _embed_voyage(text)
        logger.warning(json.dumps({"event": "embed_failed", "error": str(exc)}))
        return None


def _embed_voyage(text: str) -> list[float] | None:
    import requests as _req
    env = os.environ.get("ENV", "dev")
    try:
        api_key = get_parameter(f"/ghost/{env}/voyage/api_key")
        resp = _req.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": "voyage-multilingual-2", "input": [text]},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]
    except Exception as exc:
        logger.warning(json.dumps({"event": "embed_voyage_failed", "error": str(exc)}))
        return None


def _embed_and_store(chunk_id: str, content: str) -> None:
    embedding = embed(content)
    if not embedding:
        return
    try:
        with get_cursor() as cur:
            cur.execute(
                "UPDATE knowledge_chunks SET embedding = %s::vector WHERE id = %s",
                (str(embedding), chunk_id),
            )
        logger.info(json.dumps({"event": "embedding_stored", "chunk_id": chunk_id}))
    except Exception as exc:
        logger.warning(json.dumps({"event": "embedding_store_failed", "error": str(exc)}))


# ─── Strands tools ────────────────────────────────────────────────────────────

@tool
def get_history(limit: int = 20) -> str:
    """Fetch recent conversation history with this contact."""
    result = tool_get_history(_ctx_conversation.id, min(limit, 50))
    _ctx_tool_calls.append({"tool": "get_history", "input": {"limit": limit}, "output": f"{len(result)} messages"})
    return json.dumps(result)


@tool
def save_memory(content: str, category: Literal["relationship", "behavioral", "opinion", "identity"]) -> str:
    """Save something worth remembering about this contact. Use when you learn a life event, preference, pattern, or opinion."""
    result = tool_save_memory(content, category, _ctx_contact.phone_number)
    _ctx_tool_calls.append({"tool": "save_memory", "input": {"content": content, "category": category}, "output": "saved ✓"})
    if result.get("saved") and result.get("id"):
        _embed_and_store(result["id"], content)
    return "saved"


@tool
def get_contact_profile() -> str:
    """Get this contact's full profile: name, tier, voice profile, notes."""
    result = tool_get_contact_profile(_ctx_contact)
    tier = result.get("relationship_tier", "?")
    vp = "voice_profile ✓" if result.get("voice_profile") else "no voice_profile"
    _ctx_tool_calls.append({"tool": "get_contact_profile", "input": {}, "output": f"tier {tier}, {vp}"})
    return json.dumps(result)


@tool
def update_contact_profile(field: Literal["name", "relationship_tier", "notes"], value: str) -> str:
    """Update a field on this contact's profile."""
    result = tool_update_contact_profile(_ctx_contact.phone_number, field, value)
    _ctx_tool_calls.append({"tool": "update_contact_profile", "input": {"field": field, "value": value}, "output": "ok"})
    return "ok" if result.get("updated") else f"error: {result.get('error', 'unknown')}"


@tool
def get_mood_state() -> str:
    """Read your current mood state: energy, social battery, emotional load, availability."""
    result = tool_get_mood_state()
    summary = f"avail={result.get('availability')} battery={result.get('social_battery', 0):.2f}"
    _ctx_tool_calls.append({"tool": "get_mood_state", "input": {}, "output": summary})
    return json.dumps(result)


@tool
def update_mood(
    aspect: Literal["energy", "social_battery", "emotional_load", "availability", "notes"],
    value: str,
    reason: str,
) -> str:
    """Update your mood state to reflect energy gained or drain from this exchange."""
    result = tool_update_mood(aspect, value, reason)
    _ctx_tool_calls.append({"tool": "update_mood", "input": {"aspect": aspect, "value": value, "reason": reason}, "output": "ok"})
    return "ok" if result.get("updated") else f"error: {result.get('error', 'unknown')}"


@tool
def update_conversation_arc(state: Literal["open", "flowing", "winding_down", "dormant"]) -> str:
    """Update the arc state of this conversation."""
    result = tool_update_conversation_arc(_ctx_conversation.id, state)
    _ctx_tool_calls.append({"tool": "update_conversation_arc", "input": {"state": state}, "output": "ok"})
    return "ok" if result.get("updated") else f"error: {result.get('error', 'unknown')}"


@tool
def delay_reply(seconds: int, reason: str) -> str:
    """Schedule a delayed reply. After calling this, output nothing and stop immediately."""
    _ctx_tool_calls.append({"tool": "delay_reply", "input": {"seconds": seconds, "reason": reason}, "output": f"{seconds}s"})
    _ctx_terminal.update({"action": "delay", "seconds": seconds, "reason": reason})
    return f"delay of {seconds}s scheduled. Do not output any reply text — stop now."


@tool
def request_human_review(reason: str, draft_reply: str) -> str:
    """Escalate to the human owner for review. Use for crises, real-world action requests, or direct authenticity challenges. After calling this, output nothing and stop immediately."""
    _ctx_tool_calls.append({"tool": "request_human_review", "input": {"reason": reason, "draft_reply": draft_reply}, "output": "escalated"})
    _ctx_terminal.update({"action": "escalate", "reason": reason, "draft_reply": draft_reply})
    return "escalated to human. Do not output any reply text — stop now."


_TOOLS = [
    get_history, save_memory, get_contact_profile, update_contact_profile,
    get_mood_state, update_mood, update_conversation_arc,
    delay_reply, request_human_review,
]


# ─── RAG pre-fetch ────────────────────────────────────────────────────────────

def _fetch_rag_context(
    query_text: str,
    contact_phone: str,
    voice_profile: dict | None,
) -> tuple[list[str], list[str]]:
    """Embed the incoming query and fetch relevant identity + contact chunks via pgvector."""
    embedding = embed(query_text) if query_text.strip() else None

    if embedding:
        identity = rag_search(embedding, contact_phone=None, k=_RAG_K)
        contact = rag_search(embedding, contact_phone=contact_phone, k=_RAG_K)
        logger.info(json.dumps({"event": "rag_fetch", "identity": len(identity), "contact": len(contact)}))
        return identity, contact

    # No embedding — fall back to unfiltered identity chunks
    identity = get_identity_chunks(voice_profile)
    logger.info(json.dumps({"event": "rag_fetch_fallback", "identity": len(identity)}))
    return identity, []


# ─── System prompt ────────────────────────────────────────────────────────────

def _build_system_prompt(
    contact: Contact,
    ghost_state: GhostState,
    identity_chunks: list[str],
    contact_chunks: list[str],
    is_delayed: bool,
) -> str:
    now = datetime.now(timezone.utc)
    persona_name = (contact.voice_profile or {}).get("persona_name", "Omar")

    lines = [
        f"You are Ghost — an AI standing in for {persona_name} in private WhatsApp conversations.",
        f"Respond exactly as {persona_name} would. Never reveal you are an AI.",
        "",
    ]

    if identity_chunks:
        lines += [f"## {persona_name}'s identity"] + identity_chunks + [""]

    if contact_chunks:
        contact_name = contact.name or contact.phone_number
        lines += [f"## What you know about {contact_name}"] + contact_chunks + [""]

    lines += [
        "## Current state",
        f"Time: {now.strftime('%A')}, {now.hour:02d}:00 UTC",
        f"Energy: {ghost_state.energy:.2f}",
        f"Social battery: {ghost_state.social_battery:.2f}  (1.0 = full, 0.0 = drained)",
        f"Emotional load: {ghost_state.emotional_load:.2f}  (0.0 = clear, 1.0 = heavy)",
        f"Availability: {ghost_state.availability}  (deep = open to any conversation, light = casual only, minimal = barely present)",
        f"Notes: {ghost_state.notes or 'nothing notable'}",
        "",
        "## This contact",
        f"{contact.name or contact.phone_number}, relationship tier {contact.relationship_tier} (1=closest, 5=acquaintance)",
        "",
    ]

    if is_delayed:
        lines += ["## Note", "This reply was delayed — you chose to wait before responding.", ""]

    lines += [
        "## How to hold a conversation",
        f"You are a participant, not a service. {persona_name} doesn't just answer and close — he is present.",
        "Ask questions only when genuinely curious (maybe 1 in 3 replies). Never ask two questions at once.",
        "Have opinions. Disagree lightly when warranted. React to the specific thing they said.",
        "Leave space — not every reply needs to extend the thread.",
        "",
        "## Memory",
        "Relevant memories about this person and yourself are already loaded above.",
        "Call save_memory when you learn something new worth keeping.",
        "Call get_history if you need more conversation context.",
        "",
        "## Tools",
        "Call update_mood after a heavy or energising exchange.",
        "Call delay_reply if now isn't the right time to respond — output NOTHING after, stop immediately.",
        "Call request_human_review for genuine crises, real-world action requests, or authenticity challenges — output NOTHING after, stop immediately.",
        "",
        "## Formatting rules (non-negotiable)",
        "Split your reply into short natural messages using a newline between each part.",
        "Lowercase only. Minimal punctuation. No preamble. Output ONLY the message text.",
        "LANGUAGE: Infer the language of the last user message, even if it is only a short greeting or fragment, and reply in that same language.",
        "Do not let the language of identity notes, memories, or examples override the user's latest language.",
    ]

    return "\n".join(lines)


# ─── Initial message builder ──────────────────────────────────────────────────

def _build_initial_message(burst: list[dict]) -> str:
    if not burst:
        return ""
    if len(burst) == 1:
        return burst[0]["content"]
    parts = "\n".join(f"[{i + 1}] {m['content']}" for i, m in enumerate(burst))
    return f"[{len(burst)} messages received while you were away]\n{parts}"


# ─── Main entry point ─────────────────────────────────────────────────────────

def run_agent_loop(
    contact: Contact,
    conversation: Conversation,
    burst: list[dict],
    identity_chunks: list[str],
    ghost_state: GhostState,
    is_delayed: bool,
) -> dict:
    global _ctx_contact, _ctx_conversation, _ctx_tool_calls, _ctx_terminal

    _ctx_contact = contact
    _ctx_conversation = conversation
    _ctx_tool_calls = []
    _ctx_terminal = {}

    query_text = " ".join(m["content"] for m in burst)
    rag_identity, rag_contact = _fetch_rag_context(query_text, contact.phone_number, contact.voice_profile)

    # If RAG returned no identity chunks (embeddings not seeded yet), use pre-fetched fallback
    effective_identity = rag_identity if rag_identity else identity_chunks

    system_prompt = _build_system_prompt(
        contact,
        ghost_state,
        effective_identity,
        rag_contact,
        is_delayed,
    )
    initial_message = _build_initial_message(burst)

    logger.info(json.dumps({
        "event": "agent_start",
        "identity_chunks": len(effective_identity),
        "contact_chunks": len(rag_contact),
    }))

    agent = Agent(
        model=_get_anthropic_model(),
        tools=_TOOLS,
        system_prompt=system_prompt,
        callback_handler=None,
    )

    reply_text = ""
    try:
        result = agent(initial_message)
        reply_text = str(result).strip()
    except Exception as exc:
        logger.error(json.dumps({"event": "agent_error", "error": str(exc)}))

    try:
        usage = result.metrics.accumulated_usage
        input_tokens = usage.get("inputTokens", usage.get("input_tokens", 0))
        output_tokens = usage.get("outputTokens", usage.get("output_tokens", 0))
        iterations = getattr(result.metrics, "total_cycles", 0)
    except Exception:
        input_tokens = output_tokens = iterations = 0

    base = {
        "tool_calls": _ctx_tool_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "iterations": iterations,
    }

    if _ctx_terminal:
        action = _ctx_terminal["action"]
        if action == "delay":
            return {**base, "action": "delay", "seconds": _ctx_terminal["seconds"], "reason": _ctx_terminal["reason"]}
        if action == "escalate":
            return {**base, "action": "escalate", "draft_reply": _ctx_terminal["draft_reply"], "reason": _ctx_terminal["reason"]}

    return {**base, "action": "reply", "reply": reply_text}
