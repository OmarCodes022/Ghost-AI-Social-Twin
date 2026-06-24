import os
import uuid
from datetime import datetime

import boto3
import psycopg2
import psycopg2.extras
import voyageai

_voyage_client = None


def get_db_connection():
    ssm = boto3.client("ssm", region_name="eu-west-1")
    env = os.environ["ENV"]
    dsn = ssm.get_parameter(
        Name=f"/ghost/{env}/db/connection_string", WithDecryption=True
    )["Parameter"]["Value"]
    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def _get_voyage():
    global _voyage_client
    if not _voyage_client:
        ssm = boto3.client("ssm", region_name="eu-west-1")
        env = os.environ["ENV"]
        api_key = ssm.get_parameter(
            Name=f"/ghost/{env}/voyage/api_key", WithDecryption=True
        )["Parameter"]["Value"]
        _voyage_client = voyageai.Client(api_key=api_key)
    return _voyage_client


def embed(text: str) -> list:
    result = _get_voyage().embed([text], model="voyage-3")
    return result.embeddings[0]


def insert_memory(
    conn,
    content: str,
    category: str,
    language: str,
    importance: float,
    contact_phone: str = None,
    source_conversation: str = None,
) -> None:
    embedding = embed(content)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO memories (
                id, contact_phone, category, content, language,
                embedding, importance, created_at, created_by, source_conversation
            ) VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s, 'onboarding', %s)
            """,
            (
                str(uuid.uuid4()),
                contact_phone,
                category,
                content,
                language,
                embedding,
                importance,
                datetime.utcnow(),
                source_conversation,
            ),
        )
    conn.commit()
