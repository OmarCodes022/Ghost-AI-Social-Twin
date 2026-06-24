"""
Agent 3 - Memory Processor

Job: after a conversation closes, read the full transcript and extract
everything worth keeping into structured DB signals. Pure extraction -
no Ghost identity, no judgment, no tool calls.

How it works:
  1. Triggered by memory-processing-queue (SQS) with {conversation_id, contact_phone}
  2. Fetches the closed conversation + all messages + contact profile from DB
  3. Sends the full transcript to Claude Haiku (Bedrock) with a structured prompt
  4. Haiku returns JSON: attitude shift, quality score, emotional tone, summary,
     unresolved threads, new facts, knowledge gap resolutions
  5. Handler writes all of it back to DB:
     - contact_state: updated attitude score, trend, quality avg
     - conversations: quality, tone, summary, unresolved_threads
     - memories: new facts embedded via Voyage-3
     - contact_knowledge_gaps: resolved fields marked done

Model calls: extract_signals() line 48 (Haiku), embed() line 83 (Voyage-3).
"""
import json
import logging
import os

from .db import (
    fetch_contact,
    fetch_contact_state,
    fetch_conversation,
    fetch_messages,
    insert_memory,
    resolve_knowledge_gap,
    update_contact_state,
    update_conversation,
)
from .processor import embed, extract_signals

log = logging.getLogger(__name__)
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def lambda_handler(event, _context):
    for record in event.get("Records", []):
        try:
            _process(json.loads(record["body"]))
        except Exception as exc:
            log.exception("agent3 failed for record: %s", exc)
            raise  # let SQS retry


def _process(payload: dict) -> None:
    conv_id = payload["conversation_id"]
    phone = payload["contact_phone"]

    conversation = fetch_conversation(conv_id)
    if not conversation:
        log.warning("conversation %s not found", conv_id)
        return

    messages = fetch_messages(conv_id)
    if not messages:
        log.info("no messages for conversation %s - skipping", conv_id)
        return

    contact = fetch_contact(phone)
    contact_state = fetch_contact_state(phone)
    language = contact.get("language_primary", "french")

    # Model call to analyze
    signals = extract_signals(conversation, messages, contact, contact_state)

    # Compute new attitude score (clamped)
    old_score = contact_state.get("current_attitude_score", 0.0)
    new_score = max(-1.0, min(1.0, old_score + signals.get("attitude_shift", 0.0)))
    trend = signals.get("attitude_trend", "stable")

    # Trend duration: increment if same direction, reset if changed
    old_trend = contact_state.get("attitude_trend", "stable")
    old_duration = contact_state.get("attitude_trend_duration", 0)
    duration = (old_duration + 1) if trend == old_trend else 1

    update_contact_state(
        phone,
        new_score,
        trend,
        duration,
        signals.get("quality_score", 0.5),
        signals.get("emotional_tone", "neutral"),
    )

    update_conversation(
        conv_id,
        signals.get("quality_score", 0.5),
        signals.get("emotional_tone", "neutral"),
        signals.get("summary", ""),
        signals.get("unresolved_threads", []),
    )

    # Embed and insert new facts into memories
    for fact in signals.get("new_facts", []):
        content = fact.get("content", "")
        if not content:
            continue
        try:
            embedding = embed(content)
            insert_memory(
                phone,
                content,
                fact.get("category", "fact"),
                language,
                fact.get("importance", 0.6),
                embedding,
                conv_id,
            )
        except Exception as exc:
            log.warning("failed to embed/insert fact: %s", exc)

    # Resolve knowledge gaps that were filled in this conversation
    for gap in signals.get("knowledge_gap_resolutions", []):
        field = gap.get("field")
        if field:
            resolve_knowledge_gap(phone, field)

    log.info(
        "agent3 done conv=%s phone=%s facts=%d gaps_resolved=%d",
        conv_id, phone,
        len(signals.get("new_facts", [])),
        len(signals.get("knowledge_gap_resolutions", [])),
    )
