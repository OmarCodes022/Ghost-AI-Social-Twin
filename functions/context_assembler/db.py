import os
import boto3
import psycopg2
import psycopg2.extras
from datetime import datetime

from models import GhostState, Contact, ContactState, Message, LifeEvent, FewShot

_conn = None

HISTORY_LIMIT = 30
LIFE_EVENTS_LIMIT = 10
FEW_SHOTS_LIMIT = 6


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

    _conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    _conn.autocommit = True
    return _conn


def fetch_ghost_state() -> GhostState:
    with _get_conn().cursor() as cur:
        cur.execute("SELECT energy, mood_summary, last_reflection_at FROM ghost_state WHERE id = 1")
        row = cur.fetchone()
    return GhostState(
        energy=row["energy"],
        mood_summary=row["mood_summary"],
        last_reflection_at=row["last_reflection_at"].isoformat() if row["last_reflection_at"] else None,
    )


def fetch_contact(phone: str) -> Contact:
    with _get_conn().cursor() as cur:
        cur.execute(
            "SELECT phone_number, name, relationship_tier, platform, active FROM contacts WHERE phone_number = %s",
            (phone,),
        )
        row = cur.fetchone()
    if not row:
        raise ValueError(f"contact {phone} not found")
    return Contact(**row)


def fetch_contact_state(phone: str) -> ContactState:
    with _get_conn().cursor() as cur:
        cur.execute(
            "SELECT status, last_seen_at, last_message_at, ghost_notes FROM contact_state WHERE contact_phone = %s",
            (phone,),
        )
        row = cur.fetchone()
    if not row:
        return ContactState(status="idle", last_seen_at=None, last_message_at=None, ghost_notes={})
    return ContactState(
        status=row["status"],
        last_seen_at=row["last_seen_at"].isoformat() if row["last_seen_at"] else None,
        last_message_at=row["last_message_at"].isoformat() if row["last_message_at"] else None,
        ghost_notes=row["ghost_notes"] or {},
    )


def fetch_per_person_rules(phone: str) -> list[str]:
    with _get_conn().cursor() as cur:
        cur.execute(
            "SELECT rule FROM per_person_rules WHERE contact_phone = %s ORDER BY created_at",
            (phone,),
        )
        return [row["rule"] for row in cur.fetchall()]


def fetch_conversation_history(phone: str) -> list[Message]:
    with _get_conn().cursor() as cur:
        cur.execute(
            """
            SELECT m.role, m.content, m.sent_at
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE m.contact_phone = %s AND c.ended_at IS NULL
            ORDER BY m.sent_at DESC
            LIMIT %s
            """,
            (phone, HISTORY_LIMIT),
        )
        rows = cur.fetchall()
    return [
        Message(role=r["role"], content=r["content"], sent_at=r["sent_at"].isoformat())
        for r in reversed(rows)
    ]


def fetch_life_events() -> list[LifeEvent]:
    with _get_conn().cursor() as cur:
        cur.execute(
            "SELECT event_type, description, event_date, importance FROM life_events ORDER BY importance DESC, event_date DESC LIMIT %s",
            (LIFE_EVENTS_LIMIT,),
        )
        rows = cur.fetchall()
    return [
        LifeEvent(
            event_type=r["event_type"],
            description=r["description"],
            event_date=r["event_date"].isoformat() if r["event_date"] else None,
            importance=r["importance"],
        )
        for r in rows
    ]


def fetch_few_shots(phone: str, limit: int = FEW_SHOTS_LIMIT) -> list[FewShot]:
    with _get_conn().cursor() as cur:
        cur.execute(
            """
            SELECT scenario, input_message, ideal_response FROM omar_few_shots
            WHERE contact_phone = %s OR contact_phone IS NULL
            ORDER BY contact_phone NULLS LAST, created_at DESC
            LIMIT %s
            """,
            (phone, limit),
        )
        rows = cur.fetchall()
    return [FewShot(**r) for r in rows]
