"""ghost_memory_retriever  (stub)

Performs a pgvector cosine similarity search over ``knowledge_chunks`` to
surface relevant memories for the response generator.
Phase 2 will embed the inbound message with an embeddings model and execute:

    SELECT content, 1 - (embedding <=> %s::vector) AS score
    FROM knowledge_chunks
    WHERE contact_phone = %s OR contact_phone IS NULL
    ORDER BY embedding <=> %s::vector
    LIMIT %s

For now: returns an empty list.
"""
import json
import logging
import os
from typing import Any

from models import MemoryRetrieverRequest, MemoryRetrieverResponse

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def lambda_handler(event: dict, context: Any) -> dict:
    logger.info(json.dumps({"event": "memory_retriever_invoked"}))

    request = MemoryRetrieverRequest(**event)

    # Stub: no memory chunks.
    response = MemoryRetrieverResponse(chunks=[])

    return response.model_dump(mode="json")
