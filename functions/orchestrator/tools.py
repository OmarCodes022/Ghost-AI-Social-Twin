"""Tool handlers + Anthropic tool schema for the Ghost agent loop."""
import json
import logging
import uuid
from typing import Any

from db import get_cursor
from models import ArcState
from db_helpers import get_ghost_state

logger = logging.getLogger(__name__)


# ─── Tool handlers ────────────────────────────────────────────────────────────

def tool_search_memories(query: str, contact_phone: str) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT content, category, source,
                   ts_rank(to_tsvector('english', content), plainto_tsquery('english', %s)) AS score
            FROM knowledge_chunks
            WHERE (contact_phone = %s OR contact_phone IS NULL)
              AND to_tsvector('english', content) @@ plainto_tsquery('english', %s)
            ORDER BY score DESC
            LIMIT 8
            """,
            (query, contact_phone, query),
        )
        return [dict(row) for row in cur.fetchall()]


def tool_get_contact_profile(contact) -> dict:
    return {
        "name": contact.name,
        "phone_number": contact.phone_number,
        "relationship_tier": contact.relationship_tier,
        "voice_profile": contact.voice_profile,
        "notes": contact.notes,
        "last_interaction": contact.last_interaction.isoformat() if contact.last_interaction else None,
        "interaction_frequency": contact.interaction_frequency,
    }


def tool_get_history(conversation_id: str, limit: int) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT role, content, sent_at
            FROM (
                SELECT role, content, sent_at
                FROM messages
                WHERE conversation_id = %s
                ORDER BY sent_at DESC
                LIMIT %s
            ) sub
            ORDER BY sent_at ASC
            """,
            (conversation_id, min(limit, 50)),
        )
        return [{"role": r["role"], "content": r["content"], "sent_at": r["sent_at"].isoformat()} for r in cur.fetchall()]


def tool_save_memory(content: str, category: str, contact_phone: str) -> dict:
    valid = {"identity", "opinion", "relationship", "behavioral"}
    if category not in valid:
        category = "relationship"
    chunk_id = str(uuid.uuid4())
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO knowledge_chunks (id, category, content, contact_phone, source, created_at) VALUES (%s, %s, %s, %s, 'learned', NOW())",
            (chunk_id, category, content, contact_phone),
        )
    logger.info(json.dumps({"event": "memory_saved", "category": category, "id": chunk_id}))
    return {"saved": True, "id": chunk_id}


def tool_update_contact_profile(phone: str, field: str, value: str) -> dict:
    allowed = {"name", "relationship_tier", "notes"}
    if field not in allowed:
        return {"error": f"field '{field}' not updatable. Allowed: {sorted(allowed)}"}
    with get_cursor() as cur:
        cur.execute(f"UPDATE contacts SET {field} = %s WHERE phone_number = %s", (value, phone))
    logger.info(json.dumps({"event": "contact_profile_updated", "field": field}))
    return {"updated": True, "field": field, "value": value}


def tool_get_mood_state() -> dict:
    state = get_ghost_state()
    return {
        "energy": state.energy,
        "social_battery": state.social_battery,
        "emotional_load": state.emotional_load,
        "availability": state.availability,
        "notes": state.notes,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def tool_update_mood(aspect: str, value: Any, reason: str) -> dict:
    allowed = {"energy", "social_battery", "emotional_load", "availability", "notes"}
    if aspect not in allowed:
        return {"error": f"aspect '{aspect}' not recognised. Allowed: {sorted(allowed)}"}
    with get_cursor() as cur:
        cur.execute(f"UPDATE ghost_state SET {aspect} = %s, updated_at = NOW() WHERE id = 1", (value,))
    logger.info(json.dumps({"event": "mood_updated", "aspect": aspect, "value": value, "reason": reason}))
    return {"updated": True, "aspect": aspect, "value": value}


def tool_update_conversation_arc(conversation_id: str, state: str) -> dict:
    valid = {s.value for s in ArcState}
    if state not in valid:
        return {"error": f"invalid state '{state}'. Valid: {sorted(valid)}"}
    with get_cursor() as cur:
        cur.execute("UPDATE conversations SET arc_state = %s WHERE id = %s", (state, conversation_id))
    logger.info(json.dumps({"event": "arc_updated", "state": state}))
    return {"updated": True, "state": state}


# ─── Tool output summariser ───────────────────────────────────────────────────

def summarise_tool_output(tool_name: str, result: Any) -> str:
    if isinstance(result, dict) and "error" in result:
        return f"error: {result['error']}"
    if tool_name == "search_memories":
        n = len(result) if isinstance(result, list) else 0
        return f"{n} chunk{'s' if n != 1 else ''}" if n else "no results"
    if tool_name == "get_history":
        n = len(result) if isinstance(result, list) else 0
        return f"{n} message{'s' if n != 1 else ''}"
    if tool_name == "get_contact_profile":
        if isinstance(result, dict):
            tier = result.get("relationship_tier", "?")
            vp = "voice_profile ✓" if result.get("voice_profile") else "no voice_profile"
            return f"tier {tier}, {vp}"
        return "ok"
    if tool_name == "save_memory":
        return "saved ✓" if isinstance(result, dict) and result.get("saved") else str(result)
    if tool_name == "get_mood_state":
        if isinstance(result, dict):
            return f"avail={result.get('availability')} battery={result.get('social_battery', 0):.2f}"
        return "ok"
    if tool_name in ("update_contact_profile", "update_mood", "update_conversation_arc"):
        return "ok" if isinstance(result, dict) and result.get("updated") else str(result)
    return "ok"


# ─── Anthropic tool schema ────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "search_memories",
        "description": "Search long-term memory for information about this contact or about yourself. Use when you need to recall something specific — a past conversation, a detail they told you, a shared experience, or something about your own opinions/life.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "Natural language search query"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_contact_profile",
        "description": "Get the full profile for this contact: name, relationship tier, voice profile (their communication style), notes, interaction frequency.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_history",
        "description": "Fetch recent conversation history with this contact. Use when you need context beyond what's already in the current messages.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Number of messages to fetch (max 50)", "default": 20}},
            "required": [],
        },
    },
    {
        "name": "save_memory",
        "description": "Save something to long-term memory about this contact. Use when you learn something worth keeping: a life event, a preference, something they told you, a pattern you noticed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The fact or observation to remember"},
                "category": {
                    "type": "string",
                    "enum": ["relationship", "behavioral", "opinion", "identity"],
                    "description": "relationship = facts about them, behavioral = patterns/style, opinion = their views, identity = about yourself",
                },
            },
            "required": ["content", "category"],
        },
    },
    {
        "name": "update_contact_profile",
        "description": "Update a structured field on the contact record. Use when you infer their name, a tier change, or want to add a note.",
        "input_schema": {
            "type": "object",
            "properties": {
                "field": {"type": "string", "enum": ["name", "relationship_tier", "notes"]},
                "value": {"type": "string", "description": "New value for the field"},
            },
            "required": ["field", "value"],
        },
    },
    {
        "name": "get_mood_state",
        "description": "Read your current persistent mood state: energy, social battery, emotional load, availability mode, and any notes set externally.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "update_mood",
        "description": "Update your mood state after or during a conversation. Use to reflect drain, heaviness, or energy gained.",
        "input_schema": {
            "type": "object",
            "properties": {
                "aspect": {"type": "string", "enum": ["energy", "social_battery", "emotional_load", "availability", "notes"]},
                "value": {"description": "New value (float for energy/social_battery/emotional_load, string for availability/notes)"},
                "reason": {"type": "string", "description": "Why you're updating this"},
            },
            "required": ["aspect", "value", "reason"],
        },
    },
    {
        "name": "delay_reply",
        "description": "Decide not to reply right now and schedule a delayed response. Use based on context: it's very late, you're unavailable, the message doesn't need an immediate reply.",
        "input_schema": {
            "type": "object",
            "properties": {
                "seconds": {"type": "integer", "description": "How long to wait before replying (max 900s via SQS)"},
                "reason": {"type": "string", "description": "Why you're delaying"},
            },
            "required": ["seconds", "reason"],
        },
    },
    {
        "name": "request_human_review",
        "description": "Send this conversation to the human for review before replying. Use for: genuine crisis or distress, requests for real-world action, direct 'are you real?' challenges, or anything you feel genuinely uncertain about.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why you're escalating"},
                "draft_reply": {"type": "string", "description": "Your proposed reply — the human can send, edit, or skip it"},
            },
            "required": ["reason", "draft_reply"],
        },
    },
    {
        "name": "update_conversation_arc",
        "description": "Update the arc state of this conversation. Use when you sense the conversation is naturally winding down or has gone dormant.",
        "input_schema": {
            "type": "object",
            "properties": {"state": {"type": "string", "enum": ["open", "flowing", "winding_down", "dormant"]}},
            "required": ["state"],
        },
    },
]
