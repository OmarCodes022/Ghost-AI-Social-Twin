"""
Agent 2 - Ghost (core identity)

The main brain. Ghost's full identity loaded on every call. Two modes via dynamic system prompt:

Response mode (perception-output-queue):
  1. Receives PerceptionOutput from Agent 1 — classified incoming message burst
  2. Calls context_assembler Lambda (sync) to build Tier 1 context package
  3. Loads identity from DB (identity memories + voice profiles) for system prompt
  4. Runs claude-sonnet via Bedrock with SQL + RAG tools until stop_reason=end_turn
  5. Parses <ghost_decision> JSON block from final assistant text
  6. Executes: reply -> outbound-queue | defer -> defer_conditions | escalate -> escalation-queue
  7. Always writes ghost_reflections entry

Heartbeat mode (heartbeat-queue):
  1. Receives {phone, reason, condition_id} from pulse
  2. Loads ghost_state, builds lighter context (no conversation history pre-loaded)
  3. Same Bedrock tool loop — Ghost decides and acts via SQL tool within the loop
  4. Executes outbound message if action is reach_out or reply_deferred
  5. Always updates last_heartbeat_action/at and writes reflection

Tool loop: max 8 rounds, exits on stop_reason=end_turn.
Model: anthropic.claude-sonnet-4-5 (see template.yaml IAM policy).
"""
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone

import boto3

from db import (
    fetch_identity_memories,
    fetch_voice_profiles,
    open_conversation,
    update_conversation_close_condition,
    update_last_heartbeat,
    write_defer_condition,
    write_reflection,
)
from prompts import build_system_prompt, format_heartbeat_context, format_response_context
from tools import TOOL_DEFINITIONS, execute_tool, execute_sql

log = logging.getLogger(__name__)
log.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

MODEL_ID = "eu.anthropic.claude-sonnet-4-5-20250929-v1:0"
MAX_TOOL_ROUNDS = 8

_bedrock = None
_lambda_client = None
_sqs = None


def _get_bedrock():
    global _bedrock
    if not _bedrock:
        _bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
    return _bedrock


def _get_lambda():
    global _lambda_client
    if not _lambda_client:
        _lambda_client = boto3.client("lambda", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
    return _lambda_client


def _get_sqs():
    global _sqs
    if not _sqs:
        _sqs = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
    return _sqs


def lambda_handler(event, _context):
    for record in event.get("Records", []):
        try:
            payload = json.loads(record["body"])
            if "contact_phone" in payload:
                _run_response_mode(payload)
            elif "phone" in payload:
                _run_heartbeat_mode(payload)
            else:
                log.error("unknown payload shape: keys=%s", list(payload.keys()))
        except Exception as exc:
            log.exception("agent_ghost failed: %s", exc)
            raise  # let SQS retry


def _build_system(mode: str) -> str:
    return build_system_prompt(fetch_identity_memories(), fetch_voice_profiles(), mode)


def _run_response_mode(perception_output: dict) -> None:
    phone = perception_output["contact_phone"]
    conv_id = perception_output.get("conversation_id")

    # Tier 1 context from context_assembler Lambda (synchronous invoke)
    resp = _get_lambda().invoke(
        FunctionName=os.environ["CONTEXT_ASSEMBLER_FUNCTION"],
        InvocationType="RequestResponse",
        Payload=json.dumps({"contact_phone": phone, "perception": perception_output}),
    )
    tier1 = json.loads(resp["Payload"].read())

    now = datetime.now(timezone.utc)
    text = _bedrock_tool_loop(
        _build_system("response"),
        format_response_context(tier1, now),
    )
    decision = _extract_decision(text)
    action = decision.get("action", "nothing")

    if action == "reply":
        _dispatch_reply(phone, conv_id, decision)
    elif action == "defer":
        write_defer_condition(
            phone,
            decision.get("defer_condition") or {"type": "time_elapsed", "hours": 24},
            decision.get("defer_reasoning", ""),
        )
    elif action == "escalate":
        _dispatch_escalation(phone, perception_output, decision.get("escalation_reason", ""))

    write_reflection(phone, "response", decision.get("scratchpad", ""), action)
    log.info("response mode done phone=%s action=%s", phone, action)


def _run_heartbeat_mode(payload: dict) -> None:
    phone = payload["phone"]

    # Pull ghost_state for context header
    ghost_state = {}
    raw = execute_sql(
        "SELECT mood, social_battery, emotional_load, current_focus, whats_on_mind "
        "FROM ghost_state LIMIT 1"
    )
    try:
        rows = json.loads(raw)
        if rows:
            ghost_state = rows[0]
    except Exception:
        pass

    now = datetime.now(timezone.utc)
    text = _bedrock_tool_loop(
        _build_system("heartbeat"),
        format_heartbeat_context(payload, ghost_state, now),
    )
    decision = _extract_decision(text)
    action = decision.get("action", "nothing")

    if action in ("reach_out", "reply_deferred"):
        msg = decision.get("message", "")
        if msg:
            conv_id = open_conversation(phone)
            close_cond = decision.get("close_condition") or {"type": "time_elapsed", "hours": 4}
            update_conversation_close_condition(conv_id, close_cond)
            _send_outbound(phone, msg, decision.get("send_delay_minutes", 0))

    write_reflection(phone, f"heartbeat_{action}", decision.get("scratchpad", ""), action)
    update_last_heartbeat(phone, action)
    log.info("heartbeat mode done phone=%s action=%s", phone, action)


def _bedrock_tool_loop(system: str, human_turn: str) -> str:
    messages = [{"role": "user", "content": human_turn}]
    bedrock = _get_bedrock()

    for _ in range(MAX_TOOL_ROUNDS):
        result = json.loads(
            bedrock.invoke_model(
                modelId=MODEL_ID,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4096,
                    "system": system,
                    "tools": TOOL_DEFINITIONS,
                    "messages": messages,
                }),
                contentType="application/json",
                accept="application/json",
            )["body"].read()
        )

        stop_reason = result.get("stop_reason")
        content = result.get("content", [])
        messages.append({"role": "assistant", "content": content})

        if stop_reason == "end_turn":
            for block in reversed(content):
                if block.get("type") == "text":
                    return block["text"]
            return ""

        if stop_reason == "tool_use":
            tool_results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": execute_tool(block["name"], block["input"]),
                }
                for block in content
                if block.get("type") == "tool_use"
            ]
            messages.append({"role": "user", "content": tool_results})
        else:
            log.warning("unexpected stop_reason: %s", stop_reason)
            break

    log.warning("tool loop hit max rounds (%d), forcing final turn", MAX_TOOL_ROUNDS)
    messages.append({"role": "user", "content": "Tool budget exhausted. Output your <ghost_decision> block now based on everything gathered. No more tool calls."})
    result = json.loads(
        bedrock.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "system": system,
                "messages": messages,
            }),
            contentType="application/json",
            accept="application/json",
        )["body"].read()
    )
    for block in reversed(result.get("content", [])):
        if block.get("type") == "text":
            return block["text"]
    return ""


def _extract_decision(text: str) -> dict:
    m = re.search(r"<ghost_decision>\s*(.*?)\s*</ghost_decision>", text, re.DOTALL)
    if not m:
        log.warning("no <ghost_decision> block in response")
        return {"action": "nothing", "scratchpad": text[:500]}
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError as exc:
        log.warning("failed to parse ghost_decision: %s", exc)
        return {"action": "nothing", "scratchpad": text[:500]}


def _dispatch_reply(phone: str, conv_id: str, decision: dict) -> None:
    msg = decision.get("message", "")
    if not msg:
        log.warning("reply action but no message for phone=%s", phone)
        return
    _send_outbound(phone, msg, decision.get("send_delay_minutes", 0))
    if conv_id:
        close_cond = decision.get("close_condition") or {"type": "time_elapsed", "hours": 4}
        update_conversation_close_condition(conv_id, close_cond)


def _send_outbound(phone: str, message: str, delay_minutes: int = 0) -> None:
    _get_sqs().send_message(
        QueueUrl=os.environ["OUTBOUND_QUEUE_URL"],
        MessageBody=json.dumps({"to_phone_number": phone, "content": message}),
        MessageGroupId=phone,
        MessageDeduplicationId=str(uuid.uuid4()),
    )


def _dispatch_escalation(phone: str, perception: dict, reason: str) -> None:
    _get_sqs().send_message(
        QueueUrl=os.environ["ESCALATION_QUEUE_URL"],
        MessageBody=json.dumps({
            "contact_phone": phone,
            "contact_name": perception.get("contact_name", phone),
            "content": perception.get("content", ""),
            "reason": reason,
        }),
    )
