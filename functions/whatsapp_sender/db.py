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


def store_ghost_message(phone: str, content: str) -> None:
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM conversations WHERE contact_phone = %s AND state = 'open' "
            "ORDER BY started_at DESC LIMIT 1",
            (phone,),
        )
        row = cur.fetchone()
        if not row:
            return
        conv_id = row[0]
        cur.execute(
            "INSERT INTO messages (conversation_id, contact_phone, role, content) "
            "VALUES (%s, %s, 'ghost', %s)",
            (conv_id, phone, content),
        )
        cur.execute(
            "UPDATE contact_state SET "
            "last_interaction_at = NOW(), last_interaction_role = 'ghost', "
            "unanswered_message_flag = FALSE, updated_at = NOW() "
            "WHERE contact_phone = %s",
            (phone,),
        )
    conn.commit()
