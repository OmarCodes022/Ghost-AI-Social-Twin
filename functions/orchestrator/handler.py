"""ghost_orchestrator

Main flow controller. Receives an OrchestratorEvent from webhook_receiver,
loads (or creates) the contact and conversation in PostgreSQL, logs the inbound
message, then runs the full intelligence pipeline:

  mood_engine → timing_engine → escalation_detector → memory_retriever
  → response_generator → whatsapp_sender (or SNS escalation)
"""
import json
import logging
import os
import uuid
from typing import Any

import boto3

from db import get_cursor
from models import (
    ArcState,
    Contact,
    Conversation,
    EscalationDetectorRequest,
    EscalationDetectorResponse,
    MemoryRetrieverRequest,
    MemoryRetrieverResponse,
    Message,
    MessageRole,
    MoodEngineRequest,
    MoodEngineResponse,
    OrchestratorEvent,
    ResponseGeneratorRequest,
    ResponseGeneratorResponse,
    TelegramEscalationEvent,
    TimingEngineRequest,
    TimingEngineResponse,
    WhatsAppSenderRequest,
)

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_lambda_client: Any = None
_sns_client: Any = None
_sqs_client: Any = None


def _get_lambda_client():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda")
    return _lambda_client


def _get_sns_client():
    global _sns_client
    if _sns_client is None:
        _sns_client = boto3.client("sns")
    return _sns_client


def _get_sqs_client():
    global _sqs_client
    if _sqs_client is None:
        _sqs_client = boto3.client("sqs")
    return _sqs_client


# ─── Entry point ──────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context: Any) -> None:
    # SQS re-invocation (delayed message firing)
    if "Records" in event:
        for record in event["Records"]:
            body = json.loads(record["body"])
            _process(OrchestratorEvent(**body))
        return

    _process(OrchestratorEvent(**event))


def _process(orch_event: OrchestratorEvent) -> None:
    logger.info(json.dumps({"event": "orchestrator_invoked", "is_delayed": orch_event.is_delayed}))

    inbound = orch_event.inbound_message
    env = os.environ.get("ENV", "dev")

    contact = _load_or_create_contact(inbound.phone_number)
    conversation = _load_or_create_conversation(inbound.phone_number)

    msg = _log_message(
        conversation_id=conversation.id,
        role=MessageRole.user,
        content=inbound.content,
    )

    logger.info(
        json.dumps({
            "event": "inbound_message_logged",
            "phone": inbound.phone_number,
            "db_message_id": msg.id,
            "conversation_id": conversation.id,
        })
    )

    # ── 1. Mood engine ─────────────────────────────────────────────────────────
    mood_raw = _invoke_sync(
        f"ghost-mood-engine-{env}",
        MoodEngineRequest(
            contact_phone=inbound.phone_number,
            conversation_id=conversation.id,
            contact_context=contact.model_dump(mode="json"),
        ).model_dump(mode="json"),
    )
    mood = MoodEngineResponse(**mood_raw).mood_state

    # ── 2. Timing engine ───────────────────────────────────────────────────────
    # Skip timing on delayed re-invocations — we already waited.
    if not orch_event.is_delayed:
        timing_raw = _invoke_sync(
            f"ghost-timing-engine-{env}",
            TimingEngineRequest(
                contact_phone=inbound.phone_number,
                conversation_id=conversation.id,
                mood_state=mood,
                last_message_at=conversation.last_message_at,
            ).model_dump(mode="json"),
        )
        timing = TimingEngineResponse(**timing_raw)

        if not timing.reply_now:
            _enqueue_delay(orch_event, timing.delay_seconds, timing.reasoning)
            return

    # ── 3. Escalation detector ─────────────────────────────────────────────────
    esc_raw = _invoke_sync(
        f"ghost-escalation-detector-{env}",
        EscalationDetectorRequest(
            contact_phone=inbound.phone_number,
            message_content=inbound.content,
            conversation_id=conversation.id,
            message_id=msg.id,
        ).model_dump(mode="json"),
    )
    esc = EscalationDetectorResponse(**esc_raw)

    # ── 4. Memory retriever ────────────────────────────────────────────────────
    mem_raw = _invoke_sync(
        f"ghost-memory-retriever-{env}",
        MemoryRetrieverRequest(
            contact_phone=inbound.phone_number,
            query=inbound.content,
        ).model_dump(mode="json"),
    )
    memory = MemoryRetrieverResponse(**mem_raw)

    # ── 5. Response generator ──────────────────────────────────────────────────
    rg_raw = _invoke_sync(
        f"ghost-response-generator-{env}",
        ResponseGeneratorRequest(
            contact_phone=inbound.phone_number,
            conversation_id=conversation.id,
            inbound_message=inbound.content,
            mood_state=mood,
            memory_chunks=memory.chunks,
            voice_profile=contact.voice_profile,
        ).model_dump(mode="json"),
    )
    rg = ResponseGeneratorResponse(**rg_raw)

    # ── 6. Log agent reply ─────────────────────────────────────────────────────
    agent_msg = _log_message(
        conversation_id=conversation.id,
        role=MessageRole.agent,
        content=rg.reply,
    )

    # ── 7. Escalation → Telegram, or send directly ────────────────────────────
    if esc.is_escalation:
        _publish_escalation(
            env=env,
            contact=contact,
            original_message=inbound.content,
            proposed_reply=rg.reply,
            reason=esc.reason or "flagged by escalation detector",
            confidence=esc.confidence,
            message_id=agent_msg.id,
        )
    else:
        _invoke_whatsapp_sender(
            env=env,
            to_phone_number=inbound.phone_number,
            message=rg.reply,
            message_id=agent_msg.id,
        )


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _load_or_create_contact(phone_number: str) -> Contact:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT phone_number, name, relationship_tier, voice_profile,
                   last_interaction, interaction_frequency, notes, created_at
            FROM contacts
            WHERE phone_number = %s
            """,
            (phone_number,),
        )
        row = cur.fetchone()

        if row:
            cur.execute(
                "UPDATE contacts SET last_interaction = NOW() WHERE phone_number = %s",
                (phone_number,),
            )
            logger.info(json.dumps({"event": "contact_loaded", "phone": phone_number}))
            return Contact(**row)

        cur.execute(
            """
            INSERT INTO contacts (phone_number, relationship_tier, last_interaction,
                                  interaction_frequency, created_at)
            VALUES (%s, 5, NOW(), 0.0, NOW())
            RETURNING phone_number, name, relationship_tier, voice_profile,
                      last_interaction, interaction_frequency, notes, created_at
            """,
            (phone_number,),
        )
        row = cur.fetchone()
        logger.info(json.dumps({"event": "contact_created", "phone": phone_number}))
        return Contact(**row)


def _load_or_create_conversation(phone_number: str) -> Conversation:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, contact_phone, arc_state, started_at, last_message_at, message_count
            FROM conversations
            WHERE contact_phone = %s
              AND arc_state IN ('open', 'flowing')
            ORDER BY last_message_at DESC
            LIMIT 1
            """,
            (phone_number,),
        )
        row = cur.fetchone()

        if row:
            conv_id = str(row["id"])
            cur.execute(
                """
                UPDATE conversations
                SET last_message_at = NOW(),
                    message_count   = message_count + 1
                WHERE id = %s
                """,
                (conv_id,),
            )
            return Conversation(
                id=conv_id,
                contact_phone=row["contact_phone"],
                arc_state=ArcState(row["arc_state"]),
                started_at=row["started_at"],
                last_message_at=row["last_message_at"],
                message_count=row["message_count"],
            )

        conv_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO conversations
                (id, contact_phone, arc_state, started_at, last_message_at, message_count)
            VALUES (%s, %s, 'open', NOW(), NOW(), 1)
            RETURNING id, contact_phone, arc_state, started_at, last_message_at, message_count
            """,
            (conv_id, phone_number),
        )
        row = cur.fetchone()
        return Conversation(
            id=str(row["id"]),
            contact_phone=row["contact_phone"],
            arc_state=ArcState(row["arc_state"]),
            started_at=row["started_at"],
            last_message_at=row["last_message_at"],
            message_count=row["message_count"],
        )


def _log_message(conversation_id: str, role: MessageRole, content: str) -> Message:
    msg_id = str(uuid.uuid4())
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO messages
                (id, conversation_id, role, content, sent_at,
                 was_delayed, delay_seconds, confidence_score, escalated)
            VALUES (%s, %s, %s, %s, NOW(), false, 0, 1.0, false)
            RETURNING id
            """,
            (msg_id, conversation_id, role.value, content),
        )
        row = cur.fetchone()
        return Message(
            id=str(row["id"]),
            conversation_id=conversation_id,
            role=role,
            content=content,
        )


# ─── Downstream invocations ───────────────────────────────────────────────────

def _enqueue_delay(orch_event: OrchestratorEvent, delay_seconds: int, reason: str) -> None:
    """Put the event back on the SQS delay queue. Fires the orchestrator again after the delay."""
    queue_url = os.environ.get("DELAY_QUEUE_URL", "")
    delayed_event = orch_event.model_copy(update={"is_delayed": True})
    _get_sqs_client().send_message(
        QueueUrl=queue_url,
        MessageBody=delayed_event.model_dump_json(),
        DelaySeconds=min(delay_seconds, 900),
    )
    logger.info(
        json.dumps({
            "event": "reply_enqueued",
            "delay_seconds": delay_seconds,
            "reason": reason,
        })
    )


def _invoke_sync(function_name: str, payload: dict) -> dict:
    """Invoke a Lambda synchronously and return the parsed response."""
    response = _get_lambda_client().invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode(),
    )
    result = json.loads(response["Payload"].read())

    if response.get("FunctionError"):
        error_msg = result.get("errorMessage", str(result))
        logger.error(
            json.dumps({
                "event": "downstream_lambda_error",
                "function": function_name,
                "error": error_msg,
            })
        )
        raise RuntimeError(f"{function_name} returned error: {error_msg}")

    return result


def _invoke_whatsapp_sender(
    env: str, to_phone_number: str, message: str, message_id: str
) -> None:
    request = WhatsAppSenderRequest(
        to_phone_number=to_phone_number,
        message=message,
        message_id=message_id,
    )
    _get_lambda_client().invoke(
        FunctionName=f"ghost-whatsapp-sender-{env}",
        InvocationType="Event",
        Payload=json.dumps(request.model_dump()).encode(),
    )
    logger.info(
        json.dumps({"event": "whatsapp_sender_invoked", "to": to_phone_number})
    )


def _publish_escalation(
    env: str,
    contact: Contact,
    original_message: str,
    proposed_reply: str,
    reason: str,
    confidence: float,
    message_id: str,
) -> None:
    topic_arn = os.environ.get("ESCALATIONS_TOPIC_ARN", "")
    escalation_id = str(uuid.uuid4())

    payload = TelegramEscalationEvent(
        escalation_id=escalation_id,
        message_id=message_id,
        contact_phone=contact.phone_number,
        contact_name=contact.name,
        original_message=original_message,
        proposed_reply=proposed_reply,
        reason=reason,
        confidence=confidence,
    )

    _get_sns_client().publish(
        TopicArn=topic_arn,
        Message=payload.model_dump_json(),
    )

    logger.info(
        json.dumps({
            "event": "escalation_published",
            "escalation_id": escalation_id,
            "reason": reason,
        })
    )
