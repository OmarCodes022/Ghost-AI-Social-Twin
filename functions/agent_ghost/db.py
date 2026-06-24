import json
import os
import uuid

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
    ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
    url = ssm.get_parameter(
        Name=f"/ghost/{os.environ['ENV']}/db/connection_string",
        WithDecryption=True,
    )["Parameter"]["Value"]
    _conn = psycopg2.connect(url)
    _conn.autocommit = False
    return _conn


def fetch_identity_memories() -> list:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT content, category, importance FROM memories
            WHERE contact_phone IS NULL
            ORDER BY importance DESC
            LIMIT 40
            """
        )
        rows = cur.fetchall()
    return [{"content": r[0], "category": r[1], "importance": r[2]} for r in rows]


def fetch_voice_profiles() -> list:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT language, register, avg_message_length, formality_level,
                   emoji_behavior, sentence_structure, punctuation_habits,
                   tone_description, slang
            FROM omar_voice_profiles
            ORDER BY language
            """
        )
        rows = cur.fetchall()
    return [
        {
            "language": r[0],
            "register": r[1],
            "avg_message_length": r[2],
            "formality_level": r[3],
            "emoji_behavior": r[4],
            "sentence_structure": r[5],
            "punctuation_habits": r[6],
            "tone_description": r[7],
            "slang": r[8] or {},
        }
        for r in rows
    ]


def write_defer_condition(phone: str, condition: dict, reasoning: str) -> str:
    conn = _get_conn()
    cid = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO defer_conditions
                (id, contact_phone, condition, reason, status, created_at)
            VALUES (%s, %s, %s::jsonb, %s, 'active', NOW())
            """,
            (cid, phone, json.dumps(condition), reasoning),
        )
        cur.execute(
            """
            UPDATE contact_state
            SET unanswered_message_flag = TRUE,
                unanswered_since = COALESCE(unanswered_since, NOW()),
                updated_at = NOW()
            WHERE contact_phone = %s
            """,
            (phone,),
        )
    conn.commit()
    return cid


def write_reflection(phone: str, trigger_type: str, scratchpad: str, decision: str) -> None:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ghost_reflections
                (id, contact_phone, trigger_type, scratchpad, decision, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (str(uuid.uuid4()), phone, trigger_type, scratchpad, decision),
        )
    conn.commit()


def update_conversation_close_condition(conv_id: str, condition: dict) -> None:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE conversations
            SET close_condition = %s::jsonb,
                state = 'open',
                updated_at = NOW()
            WHERE id = %s
            """,
            (json.dumps(condition), conv_id),
        )
    conn.commit()


def open_conversation(phone: str) -> str:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM conversations WHERE contact_phone = %s AND state = 'open' LIMIT 1",
            (phone,),
        )
        row = cur.fetchone()
        if row:
            return str(row[0])
        conv_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO conversations (id, contact_phone, started_at, state) VALUES (%s, %s, NOW(), 'open')",
            (conv_id, phone),
        )
    conn.commit()
    return conv_id


def update_last_heartbeat(phone: str, action: str) -> None:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE contact_state
            SET last_heartbeat_action = %s,
                last_heartbeat_at = NOW(),
                updated_at = NOW()
            WHERE contact_phone = %s
            """,
            (action, phone),
        )
    conn.commit()
