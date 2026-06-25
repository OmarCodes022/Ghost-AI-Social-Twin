import os
import psycopg2
from ssm import get_parameter


def write_escalation(
    contact_phone: str,
    contact_name: str,
    message_content: str,
    ghost_reason: str,
) -> None:
    url = get_parameter(f"/ghost/{os.environ['ENV']}/db/connection_string")
    conn = psycopg2.connect(url)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO escalations (contact_phone, contact_name, message_content, ghost_reason)
            VALUES (%s, %s, %s, %s)
            """,
            (contact_phone, contact_name, message_content, ghost_reason),
        )
    conn.commit()
    conn.close()
