import os
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


def upsert_contact(phone: str, name: str) -> None:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO contacts (phone_number, name, relationship_tier, language_primary,
                                  texting_style, trust_level, risk_level)
            VALUES (%s, %s, 3, 'french', '{}', 0.5, 0.3)
            ON CONFLICT (phone_number) DO UPDATE SET
                name = EXCLUDED.name,
                updated_at = NOW()
            """,
            (phone, name),
        )
        cur.execute(
            """
            INSERT INTO contact_state (contact_phone, last_interaction_at, last_interaction_role,
                                       unanswered_message_flag, unanswered_since)
            VALUES (%s, NOW(), 'contact', TRUE, NOW())
            ON CONFLICT (contact_phone) DO UPDATE SET
                last_interaction_at = NOW(),
                last_interaction_role = 'contact',
                unanswered_message_flag = TRUE,
                unanswered_since = CASE
                    WHEN contact_state.unanswered_message_flag = FALSE THEN NOW()
                    ELSE contact_state.unanswered_since
                END,
                updated_at = NOW()
            """,
            (phone,),
        )
    conn.commit()


def write_attitude_shift(phone: str, shift: float) -> None:
    """Apply attitude_shift to contact_state immediately (Principle 4: understand once, store at once)."""
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE contact_state SET
                current_attitude_score = GREATEST(-1.0, LEAST(1.0,
                    current_attitude_score + %s)),
                updated_at = NOW()
            WHERE contact_phone = %s
            """,
            (shift, phone),
        )
    conn.commit()


def get_or_create_conversation(phone: str) -> str:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM conversations
            WHERE contact_phone = %s AND state = 'open'
            ORDER BY started_at DESC LIMIT 1
            """,
            (phone,),
        )
        row = cur.fetchone()
        if row:
            conv_id = str(row[0])
            cur.execute(
                "UPDATE conversations SET message_count = message_count + 1, updated_at = NOW() WHERE id = %s",
                (conv_id,),
            )
            conn.commit()
            return conv_id

        cur.execute(
            "INSERT INTO conversations (contact_phone, state, message_count) VALUES (%s, 'open', 1) RETURNING id",
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
    language: str = None,
) -> str:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO messages (conversation_id, contact_phone, role, content, language, whatsapp_message_id)
            VALUES (%s, %s, 'contact', %s, %s, %s)
            ON CONFLICT (whatsapp_message_id) DO NOTHING
            RETURNING id
            """,
            (conversation_id, contact_phone, content, language, whatsapp_message_id),
        )
        row = cur.fetchone()
    conn.commit()
    return str(row[0]) if row else None
