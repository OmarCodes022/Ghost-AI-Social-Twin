"""DB helpers for the orchestrator — contact/conversation/message CRUD, locking, traces."""
import json
import logging
import uuid
from typing import Any

from db import get_cursor
from models import ArcState, Contact, Conversation, GhostState, Message, MessageRole

logger = logging.getLogger(__name__)


def already_processed(whatsapp_message_id: str) -> bool:
    with get_cursor() as cur:
        cur.execute("SELECT id FROM messages WHERE whatsapp_message_id = %s LIMIT 1", (whatsapp_message_id,))
        return cur.fetchone() is not None


def is_superseded(conversation_id: str, my_db_message_id: str) -> bool:
    with get_cursor() as cur:
        cur.execute("SELECT sent_at FROM messages WHERE id = %s", (my_db_message_id,))
        row = cur.fetchone()
        if not row:
            return False
        cur.execute(
            "SELECT id FROM messages WHERE conversation_id = %s AND role = 'agent' AND sent_at > %s LIMIT 1",
            (conversation_id, row["sent_at"]),
        )
        return cur.fetchone() is not None


def get_burst_messages(conversation_id: str) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT content, whatsapp_message_id, sent_at
            FROM messages
            WHERE conversation_id = %s AND role = 'user'
              AND sent_at > (
                  SELECT COALESCE(MAX(sent_at), '1970-01-01'::timestamptz)
                  FROM messages WHERE conversation_id = %s AND role = 'agent'
              )
            ORDER BY sent_at ASC
            """,
            (conversation_id, conversation_id),
        )
        return [dict(r) for r in cur.fetchall()]


def acquire_reply_lock(conversation_id: str) -> bool:
    with get_cursor() as cur:
        cur.execute(
            "SELECT pg_try_advisory_xact_lock(hashtext(%s)) AS lock_acquired",
            (conversation_id,),
        )
        row = cur.fetchone()
        return bool(row["lock_acquired"]) if row else False


def load_or_create_contact(phone_number: str) -> Contact:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT phone_number, name, relationship_tier, voice_profile,
                   last_interaction, interaction_frequency, notes, created_at
            FROM contacts WHERE phone_number = %s
            """,
            (phone_number,),
        )
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE contacts SET last_interaction = NOW() WHERE phone_number = %s", (phone_number,))
            return Contact(**row)
        cur.execute(
            """
            INSERT INTO contacts (phone_number, relationship_tier, last_interaction, interaction_frequency, created_at)
            VALUES (%s, 2, NOW(), 0.0, NOW())
            RETURNING phone_number, name, relationship_tier, voice_profile,
                      last_interaction, interaction_frequency, notes, created_at
            """,
            (phone_number,),
        )
        return Contact(**cur.fetchone())


def load_or_create_conversation(phone_number: str) -> Conversation:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, contact_phone, arc_state, started_at, last_message_at, message_count
            FROM conversations
            WHERE contact_phone = %s AND arc_state IN ('open', 'flowing')
            ORDER BY last_message_at DESC LIMIT 1
            """,
            (phone_number,),
        )
        row = cur.fetchone()
        if row:
            conv_id = str(row["id"])
            cur.execute(
                "UPDATE conversations SET last_message_at = NOW(), message_count = message_count + 1 WHERE id = %s",
                (conv_id,),
            )
            return Conversation(
                id=conv_id,
                contact_phone=row["contact_phone"],
                arc_state=ArcState(row["arc_state"]),
                started_at=row["started_at"],
                last_message_at=row["last_message_at"],
                message_count=row["message_count"],
            )
        conv_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO conversations (id, contact_phone, arc_state, started_at, last_message_at, message_count)
            VALUES (%s, %s, 'open', NOW(), NOW(), 1)
            RETURNING id, contact_phone, arc_state, started_at, last_message_at, message_count
            """,
            (conv_id, phone_number),
        )
        row = cur.fetchone()
        return Conversation(
            id=str(row["id"]),
            contact_phone=row["contact_phone"],
            arc_state=ArcState(row["arc_state"]),
            started_at=row["started_at"],
            last_message_at=row["last_message_at"],
            message_count=row["message_count"],
        )


def log_message(
    conversation_id: str,
    role: MessageRole,
    content: str,
    whatsapp_message_id: str | None = None,
) -> Message:
    msg_id = str(uuid.uuid4())
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO messages
                (id, conversation_id, role, content, sent_at,
                 was_delayed, delay_seconds, confidence_score, escalated, whatsapp_message_id)
            VALUES (%s, %s, %s, %s, NOW(), false, 0, 1.0, false, %s)
            RETURNING id
            """,
            (msg_id, conversation_id, role.value, content, whatsapp_message_id),
        )
        row = cur.fetchone()
        return Message(id=str(row["id"]), conversation_id=conversation_id, role=role, content=content)


def get_identity_chunks(voice_profile: dict | None) -> list[str]:
    persona = (voice_profile or {}).get("persona", "default")
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


def get_ghost_state() -> GhostState:
    with get_cursor() as cur:
        cur.execute(
            "SELECT id, energy, social_battery, emotional_load, availability, notes, updated_at FROM ghost_state LIMIT 1"
        )
        row = cur.fetchone()
        return GhostState(**dict(row)) if row else GhostState()


def save_agent_trace(
    message_id: str | None,
    conversation_id: str,
    contact_phone: str,
    result: dict,
) -> None:
    try:
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_traces
                    (message_id, conversation_id, contact_phone, tool_calls,
                     input_tokens, output_tokens, iterations, action)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    message_id,
                    conversation_id,
                    contact_phone,
                    json.dumps(result.get("tool_calls", [])),
                    result.get("input_tokens", 0),
                    result.get("output_tokens", 0),
                    result.get("iterations", 0),
                    result.get("action", "reply"),
                ),
            )
    except Exception as exc:
        logger.warning(json.dumps({"event": "trace_save_failed", "error": str(exc)}))
