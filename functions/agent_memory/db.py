import os
import uuid
from datetime import datetime

import boto3
import psycopg2

_conn = None


def _get_conn():
    global _conn
    if _conn and not _conn.closed:
        try:
            _conn.cursor().execute("SELECT 1")
            return _conn
        except Exception:
            pass
    ssm = boto3.client("ssm", region_name=os.environ["AWS_REGION"])
    url = ssm.get_parameter(
        Name=f"/ghost/{os.environ['ENV']}/db/connection_string",
        WithDecryption=True,
    )["Parameter"]["Value"]
    _conn = psycopg2.connect(url)
    _conn.autocommit = False
    return _conn


def fetch_conversation(conv_id: str) -> dict:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, contact_phone, started_at, message_count FROM conversations WHERE id = %s",
            (conv_id,),
        )
        row = cur.fetchone()
    if not row:
        return {}
    return {"id": str(row[0]), "contact_phone": row[1], "started_at": row[2], "message_count": row[3]}


def fetch_messages(conv_id: str) -> list:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT role, content, language, sent_at FROM messages WHERE conversation_id = %s ORDER BY sent_at ASC",
            (conv_id,),
        )
        rows = cur.fetchall()
    return [{"role": r[0], "content": r[1], "language": r[2], "sent_at": r[3]} for r in rows]


def fetch_contact(phone: str) -> dict:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT name, relationship_tier, language_primary FROM contacts WHERE phone_number = %s",
            (phone,),
        )
        row = cur.fetchone()
    if not row:
        return {}
    return {"name": row[0], "relationship_tier": row[1], "language_primary": row[2]}


def fetch_contact_state(phone: str) -> dict:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT current_attitude_score, attitude_trend, attitude_trend_duration
            FROM contact_state WHERE contact_phone = %s
            """,
            (phone,),
        )
        row = cur.fetchone()
    if not row:
        return {"current_attitude_score": 0.0, "attitude_trend": "stable", "attitude_trend_duration": 0}
    return {"current_attitude_score": row[0] or 0.0, "attitude_trend": row[1] or "stable", "attitude_trend_duration": row[2] or 0}


def update_contact_state(phone: str, attitude_score: float, trend: str, trend_duration: int,
                         quality: float, tone: str) -> None:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE contact_state SET
                current_attitude_score    = %s,
                attitude_trend            = %s,
                attitude_trend_duration   = %s,
                conversation_quality_avg  = COALESCE(
                    (conversation_quality_avg * 0.7 + %s * 0.3), %s
                ),
                unanswered_message_flag   = FALSE,
                unanswered_since          = NULL,
                updated_at                = NOW()
            WHERE contact_phone = %s
            """,
            (attitude_score, trend, trend_duration, quality, quality, phone),
        )
    conn.commit()


def update_conversation(conv_id: str, quality: float, tone: str, summary: str, unresolved: list) -> None:
    import json
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE conversations SET
                quality_score       = %s,
                emotional_tone      = %s,
                summary             = %s,
                unresolved_threads  = %s::jsonb,
                updated_at          = NOW()
            WHERE id = %s
            """,
            (quality, tone, summary, json.dumps(unresolved), conv_id),
        )
    conn.commit()


def insert_memory(phone: str, content: str, category: str, language: str,
                  importance: float, embedding: list, conv_id: str) -> None:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO memories
                (id, contact_phone, category, content, language, embedding,
                 importance, created_at, created_by, source_conversation)
            VALUES (%s, %s, %s, %s, %s, %s::vector, %s, NOW(), 'agent3', %s)
            """,
            (str(uuid.uuid4()), phone, category, content, language,
             embedding, importance, conv_id),
        )
    conn.commit()


def resolve_knowledge_gap(phone: str, field: str) -> None:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE contact_knowledge_gaps
            SET status = 'resolved', resolved_at = NOW()
            WHERE contact_phone = %s AND field = %s AND status IN ('pending', 'asked')
            """,
            (phone, field),
        )
    conn.commit()
