import json
import logging
import os
import re

import boto3

from db import _get_conn

log = logging.getLogger(__name__)

# Tables Ghost is allowed to INSERT/UPDATE
_WRITE_ALLOWED = frozenset({
    "ghost_state",
    "ghost_intentions",
    "ghost_custom",
    "ghost_reflections",
    "contact_state",
    "contacts",
    "memories",
    "life_events",
    "per_person_rules",
    "contact_knowledge_gaps",
})

TOOL_DEFINITIONS = [
    {
        "name": "sql_query",
        "description": (
            "Run a SQL query against the Ghost database. "
            "SELECT is allowed on any table. "
            "INSERT/UPDATE is allowed only on: ghost_state, ghost_intentions, ghost_custom, "
            "ghost_reflections, contact_state, contacts, memories, life_events, "
            "per_person_rules, contact_knowledge_gaps. "
            "No DELETE, no DDL, no writes to messages, conversations, or defer_conditions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL statement to execute."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "rag_search",
        "description": (
            "Semantic search over Ghost's memory store (Voyage-3 multilingual embeddings). "
            "Use for episodic memories, personality impressions, past interactions, or anything "
            "you didn't know the exact query for. Works across French, English, and Arabic. "
            "Optionally filter to one contact."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query.",
                },
                "contact_phone": {
                    "type": "string",
                    "description": "Optional: restrict results to this contact's memories.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default 8, max 20).",
                    "default": 8,
                },
            },
            "required": ["query"],
        },
    },
]


def _is_write_safe(query: str) -> bool:
    q = query.strip().upper()
    if q.startswith("SELECT"):
        return True
    m = re.match(r"^(INSERT\s+INTO|UPDATE)\s+(\w+)", q)
    if not m:
        return False
    return m.group(2).lower() in _WRITE_ALLOWED


def execute_sql(query: str) -> str:
    if not _is_write_safe(query):
        return "ERROR: not permitted — only SELECT on any table, INSERT/UPDATE on ghost-owned tables only."
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute(query)
            if cur.description:
                cols = [d[0] for d in cur.description]
                rows = cur.fetchmany(50)
                return json.dumps([dict(zip(cols, row)) for row in rows], default=str)
            conn.commit()
            return f"OK: {cur.rowcount} rows affected"
    except Exception as exc:
        try:
            _get_conn().rollback()
        except Exception:
            pass
        return f"ERROR: {exc}"


_voyage_client = None


def _get_voyage():
    global _voyage_client
    if not _voyage_client:
        import voyageai
        ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
        key = ssm.get_parameter(
            Name=f"/ghost/{os.environ['ENV']}/voyage/api_key", WithDecryption=True
        )["Parameter"]["Value"]
        _voyage_client = voyageai.Client(api_key=key)
    return _voyage_client


def execute_rag(query: str, contact_phone: str = None, limit: int = 8) -> str:
    limit = min(int(limit), 20)
    try:
        embedding = _get_voyage().embed([query], model="voyage-3").embeddings[0]
        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"
        conn = _get_conn()
        with conn.cursor() as cur:
            if contact_phone:
                cur.execute(
                    """
                    SELECT content, category, importance,
                           round((1 - (embedding <=> %s::vector))::numeric, 3) AS score
                    FROM memories
                    WHERE contact_phone = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (vec_str, contact_phone, vec_str, limit),
                )
            else:
                cur.execute(
                    """
                    SELECT content, category, importance,
                           round((1 - (embedding <=> %s::vector))::numeric, 3) AS score
                    FROM memories
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (vec_str, vec_str, limit),
                )
            rows = cur.fetchall()
        return json.dumps(
            [{"content": r[0], "category": r[1], "importance": r[2], "score": float(r[3])} for r in rows]
        )
    except Exception as exc:
        return f"ERROR: {exc}"


def execute_tool(name: str, inputs: dict) -> str:
    if name == "sql_query":
        return execute_sql(inputs["query"])
    if name == "rag_search":
        return execute_rag(inputs["query"], inputs.get("contact_phone"), inputs.get("limit", 8))
    return f"ERROR: unknown tool '{name}'"
