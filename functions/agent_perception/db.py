import os
import boto3
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone

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


def upsert_contact(phone: str, name: str) -> None:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO contacts (phone_number, name)
            VALUES (%s, %s)
            ON CONFLICT (phone_number) DO UPDATE SET name = EXCLUDED.name
            """,
            (phone, name),
        )
        cur.execute(
            """
            INSERT INTO contact_state (contact_phone, last_seen_at, last_message_at)
            VALUES (%s, NOW(), NOW())
            ON CONFLICT (contact_phone) DO UPDATE
            SET last_seen_at = NOW(), last_message_at = NOW(), status = 'active'
            """,
            (phone,),
        )
    conn.commit()


def get_or_create_conversation(phone: str) -> str:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM conversations
            WHERE contact_phone = %s AND ended_at IS NULL
            ORDER BY started_at DESC LIMIT 1
            """,
            (phone,),
        )
        row = cur.fetchone()
        if row:
            conv_id = str(row[0])
            cur.execute(
                "UPDATE conversations SET last_message_at = NOW(), message_count = message_count + 1 WHERE id = %s",
                (conv_id,),
            )
            conn.commit()
            return conv_id

        cur.execute(
            """
            INSERT INTO conversations (contact_phone, message_count)
            VALUES (%s, 1) RETURNING id
            """,
            (phone,),
        )
        conv_id = str(cur.fetchone()[0])
    conn.commit()
    return conv_id


def save_message(
    conversation_id: str,
    contact_phone: str,
    content: str,
    whatsapp_message_id: str,
) -> str:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO messages (conversation_id, contact_phone, role, content, whatsapp_message_id)
            VALUES (%s, %s, 'user', %s, %s)
            ON CONFLICT (whatsapp_message_id) DO NOTHING
            RETURNING id
            """,
            (conversation_id, contact_phone, content, whatsapp_message_id),
        )
        row = cur.fetchone()
    conn.commit()
    return str(row[0]) if row else None


def mark_processed(message_id: str) -> None:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE messages SET processed = TRUE WHERE id = %s",
            (message_id,),
        )
    conn.commit()
