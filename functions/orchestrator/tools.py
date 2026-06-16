"""Underlying tool handler functions — called by @tool wrappers in agent.py."""
import json
import logging
import uuid
from typing import Any

from db import get_cursor
from models import ArcState
from db_helpers import get_ghost_state

logger = logging.getLogger(__name__)


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
