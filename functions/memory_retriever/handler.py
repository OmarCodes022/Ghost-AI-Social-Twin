"""ghost_memory_retriever

Searches knowledge_chunks for context relevant to the inbound message.

Phase 2 (ingestion): once chunks are in the DB this returns real results.
Search uses PostgreSQL full-text (tsvector/tsquery) now, and will be upgraded
to pgvector cosine similarity when the embedding pipeline is built in Phase 2.
"""
import json
import logging
import os
from typing import Any

from db import get_cursor
from models import MemoryRetrieverRequest, MemoryRetrieverResponse

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def lambda_handler(event: dict, context: Any) -> dict:
    logger.info(json.dumps({"event": "memory_retriever_invoked"}))

    request = MemoryRetrieverRequest(**event)
    chunks = _text_search(request.contact_phone, request.query, request.limit)

    logger.info(
        json.dumps({
            "event": "memory_retrieved",
            "chunks_found": len(chunks),
        })
    )

    return MemoryRetrieverResponse(chunks=chunks).model_dump(mode="json")


def _text_search(contact_phone: str, query: str, limit: int) -> list[dict]:
    """Full-text search over knowledge_chunks.

    Matches chunks belonging to this contact or global ones (contact_phone IS NULL).
    Returns empty list if no chunks exist yet (pre-ingestion).

    Phase 2 will replace this with:
        SELECT content, 1 - (embedding <=> %s::vector) AS score
        FROM knowledge_chunks
        WHERE contact_phone = %s OR contact_phone IS NULL
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT content, category, source,
                   ts_rank(to_tsvector('english', content),
                           plainto_tsquery('english', %s)) AS score
            FROM knowledge_chunks
            WHERE (contact_phone = %s OR contact_phone IS NULL)
              AND to_tsvector('english', content) @@ plainto_tsquery('english', %s)
            ORDER BY score DESC
            LIMIT %s
            """,
            (query, contact_phone, query, limit),
        )
        rows = cur.fetchall()

    return [
        {
            "content": row["content"],
            "category": row["category"],
            "source": row["source"],
            "score": float(row["score"]),
        }
        for row in rows
    ]
