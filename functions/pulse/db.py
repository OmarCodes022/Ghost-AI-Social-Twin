import os
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


def fetch_ghost_state() -> dict:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT mood, social_battery, emotional_load FROM ghost_state WHERE id = 1"
        )
        row = cur.fetchone()
    if not row:
        return {"mood": "neutral", "social_battery": 0.7, "emotional_load": 0.3}
    return {"mood": row[0], "social_battery": row[1] or 0.7, "emotional_load": row[2] or 0.3}


def fetch_all_contact_states() -> list:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                c.phone_number, c.relationship_tier, c.language_primary,
                cs.current_attitude_score, cs.attitude_trend, cs.attitude_trend_duration,
                cs.last_interaction_at, cs.last_interaction_role,
                cs.baseline_frequency, cs.unanswered_message_flag, cs.unanswered_since,
                cs.pulse_score, cs.last_heartbeat_at, cs.last_heartbeat_action
            FROM contacts c
            JOIN contact_state cs ON cs.contact_phone = c.phone_number
            """
        )
        rows = cur.fetchall()
    return [
        {
            "phone": r[0],
            "relationship_tier": r[1],
            "language_primary": r[2],
            "current_attitude_score": r[3] or 0.0,
            "attitude_trend": r[4] or "stable",
            "attitude_trend_duration": r[5] or 0,
            "last_interaction_at": r[6],
            "last_interaction_role": r[7],
            "baseline_frequency": r[8],
            "unanswered_message_flag": r[9] or False,
            "unanswered_since": r[10],
            "pulse_score": r[11] or 0.0,
            "last_heartbeat_at": r[12],
            "last_heartbeat_action": r[13],
            "defer_conditions": [],
            "open_conversations": [],
            "ghost_intentions": [],
            "life_events": [],
        }
        for r in rows
    ]


def fetch_active_defer_conditions() -> list:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, contact_phone, condition, reason, created_at, expires_at
            FROM defer_conditions
            WHERE status = 'active'
              AND (expires_at IS NULL OR expires_at > NOW())
            """
        )
        rows = cur.fetchall()
    return [
        {
            "id": str(r[0]),
            "contact_phone": r[1],
            "condition": r[2],
            "reason": r[3],
            "created_at": r[4],
            "expires_at": r[5],
        }
        for r in rows
    ]


def fetch_open_conversations() -> list:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, contact_phone, close_condition, started_at, message_count
            FROM conversations
            WHERE state = 'open' AND close_condition IS NOT NULL
            """
        )
        rows = cur.fetchall()
    return [
        {
            "id": str(r[0]),
            "contact_phone": r[1],
            "close_condition": r[2],
            "started_at": r[3],
            "message_count": r[4] or 0,
        }
        for r in rows
    ]


def fetch_active_intentions() -> list:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, contact_phone, intention, status
            FROM ghost_intentions
            WHERE status = 'active' AND contact_phone IS NOT NULL
            """
        )
        rows = cur.fetchall()
    return [
        {"id": str(r[0]), "contact_phone": r[1], "intention": r[2], "status": r[3]}
        for r in rows
    ]


def fetch_upcoming_life_events(lookahead_days: int = 14) -> list:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, contact_phone, event_type, description, event_date, lookahead_days
            FROM life_events
            WHERE event_date BETWEEN CURRENT_DATE AND CURRENT_DATE + %s
              AND contact_phone IS NOT NULL
            """,
            (lookahead_days,),
        )
        rows = cur.fetchall()
    return [
        {
            "id": str(r[0]),
            "contact_phone": r[1],
            "event_type": r[2],
            "description": r[3],
            "event_date": r[4],
            "lookahead_days": r[5] or 7,
        }
        for r in rows
    ]


def fetch_contact_messages_since(since: datetime) -> dict:
    """Returns {phone: count} of contact-role messages sent after `since`."""
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT contact_phone, COUNT(*) FROM messages
            WHERE role = 'contact' AND sent_at >= %s
            GROUP BY contact_phone
            """,
            (since,),
        )
        rows = cur.fetchall()
    return {r[0]: r[1] for r in rows}


def update_pulse_score(phone: str, score: float) -> None:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE contact_state SET
                pulse_score = %s,
                pulse_score_updated_at = NOW(),
                updated_at = NOW()
            WHERE contact_phone = %s
            """,
            (score, phone),
        )
    conn.commit()


def mark_condition_resolved(condition_id: str) -> None:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE defer_conditions SET status = 'resolved', resolved_at = NOW() WHERE id = %s",
            (condition_id,),
        )
    conn.commit()


def close_conversation(conv_id: str) -> None:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE conversations
            SET state = 'closed', closed_at = NOW(), updated_at = NOW()
            WHERE id = %s
            """,
            (conv_id,),
        )
    conn.commit()
