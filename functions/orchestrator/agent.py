"""Claude agent loop — runs until end_turn, delay_reply, or request_human_review."""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import anthropic

from models import Contact, Conversation, GhostState
from ssm import get_parameter
from tools import (
    TOOLS,
    summarise_tool_output,
    tool_get_contact_profile,
    tool_get_history,
    tool_get_mood_state,
    tool_save_memory,
    tool_search_memories,
    tool_update_contact_profile,
    tool_update_conversation_arc,
    tool_update_mood,
)

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-20250514"
_MAX_ITERATIONS = 12

_anthropic_client: anthropic.Anthropic | None = None


def get_anthropic_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        env = os.environ.get("ENV", "dev")
        api_key = get_parameter(f"/ghost/{env}/anthropic/api_key")
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
    return _anthropic_client


def run_agent_loop(
    contact: Contact,
    conversation: Conversation,
    burst: list[dict],
    identity_chunks: list[str],
    ghost_state: GhostState,
    is_delayed: bool,
) -> dict:
    """Run the Claude agent loop. Returns:
      {"action": "reply",   "reply": str, ...}
      {"action": "delay",   "seconds": int, "reason": str, ...}
      {"action": "escalate","draft_reply": str, "reason": str, ...}
    """
    system_prompt = _build_system_prompt(contact, ghost_state, identity_chunks, is_delayed)
    messages = _build_initial_messages(burst)

    tool_calls_log: list[dict] = []
    iterations = 0
    total_input_tokens = 0
    total_output_tokens = 0

    while iterations < _MAX_ITERATIONS:
        iterations += 1

        response = get_anthropic_client().messages.create(
            model=_MODEL,
            max_tokens=600,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        logger.info(json.dumps({
            "event": "claude_response",
            "stop_reason": response.stop_reason,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "iteration": iterations,
        }))

        def _base(action: str, extra: dict) -> dict:
            return {
                "action": action,
                "tool_calls": tool_calls_log,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "iterations": iterations,
                **extra,
            }

        if response.stop_reason == "end_turn":
            reply_text = "".join(b.text for b in response.content if hasattr(b, "text"))
            return _base("reply", {"reply": reply_text.strip()})

        if response.stop_reason != "tool_use":
            logger.warning(json.dumps({"event": "unexpected_stop_reason", "stop_reason": response.stop_reason}))
            break

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_input = block.input
            logger.info(json.dumps({"event": "tool_call", "tool": tool_name, "input": tool_input}))

            # Terminal tools exit immediately
            if tool_name == "delay_reply":
                tool_calls_log.append({"tool": tool_name, "input": tool_input, "output": f"{tool_input.get('seconds')}s"})
                return _base("delay", {"seconds": int(tool_input.get("seconds", 900)), "reason": tool_input.get("reason", "")})

            if tool_name == "request_human_review":
                tool_calls_log.append({"tool": tool_name, "input": tool_input, "output": "escalated"})
                return _base("escalate", {"draft_reply": tool_input.get("draft_reply", ""), "reason": tool_input.get("reason", "")})

            result_content = _execute_tool(tool_name, tool_input, contact, conversation)
            output_summary = summarise_tool_output(tool_name, result_content)
            error = result_content.get("error") if isinstance(result_content, dict) else None

            logger.info(json.dumps({"event": "tool_result", "tool": tool_name, "output": output_summary}))

            entry: dict = {"tool": tool_name, "input": tool_input, "output": output_summary}
            if error:
                entry["error"] = error
            tool_calls_log.append(entry)

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result_content),
            })

        messages.append({"role": "user", "content": tool_results})

    logger.error(json.dumps({"event": "agent_loop_limit_reached", "iterations": iterations}))
    return {"action": "reply", "reply": "", "tool_calls": tool_calls_log,
            "input_tokens": total_input_tokens, "output_tokens": total_output_tokens, "iterations": iterations}


def _execute_tool(tool_name: str, tool_input: dict, contact: Contact, conversation: Conversation) -> Any:
    try:
        if tool_name == "search_memories":
            return tool_search_memories(tool_input["query"], contact.phone_number)
        if tool_name == "get_contact_profile":
            return tool_get_contact_profile(contact)
        if tool_name == "get_history":
            return tool_get_history(conversation.id, int(tool_input.get("limit", 20)))
        if tool_name == "save_memory":
            return tool_save_memory(tool_input["content"], tool_input["category"], contact.phone_number)
        if tool_name == "update_contact_profile":
            return tool_update_contact_profile(contact.phone_number, tool_input["field"], tool_input["value"])
        if tool_name == "get_mood_state":
            return tool_get_mood_state()
        if tool_name == "update_mood":
            return tool_update_mood(tool_input["aspect"], tool_input["value"], tool_input.get("reason", ""))
        if tool_name == "update_conversation_arc":
            return tool_update_conversation_arc(conversation.id, tool_input["state"])
        return {"error": f"unknown tool: {tool_name}"}
    except Exception as exc:
        logger.error(json.dumps({"event": "tool_error", "tool": tool_name, "error": str(exc)}))
        return {"error": str(exc)}


def _build_system_prompt(contact: Contact, ghost_state: GhostState, identity_chunks: list[str], is_delayed: bool) -> str:
    now = datetime.now(timezone.utc)
    persona_name = (contact.voice_profile or {}).get("persona_name", "Omar")

    lines = [
        f"You are Ghost — an AI standing in for {persona_name} in private WhatsApp conversations.",
        f"Respond exactly as {persona_name} would. Never reveal you are an AI.",
        "",
    ]

    if identity_chunks:
        lines += [f"## {persona_name}'s identity"] + identity_chunks + [""]

    lines += [
        "## Current state",
        f"Time: {now.strftime('%A')}, {now.hour:02d}:00 UTC",
        f"Energy: {ghost_state.energy:.2f}",
        f"Social battery: {ghost_state.social_battery:.2f}  (1.0 = full, 0.0 = drained)",
        f"Emotional load: {ghost_state.emotional_load:.2f}  (0.0 = clear, 1.0 = heavy)",
        f"Availability: {ghost_state.availability}  (deep = open to any conversation, light = casual only, minimal = barely present)",
        f"Notes: {ghost_state.notes or 'nothing notable'}",
        "",
        "## This contact",
        f"{contact.name or contact.phone_number}, relationship tier {contact.relationship_tier} (1=closest, 5=acquaintance)",
        "",
    ]

    if is_delayed:
        lines += ["## Note", "This reply was delayed — you chose to wait before responding.", ""]

    lines += [
        "## How to hold a conversation",
        f"You are a participant, not a service. {persona_name} doesn't just answer and close — he is present.",
        "Ask questions only when genuinely curious (maybe 1 in 3 replies). Never ask two questions at once.",
        "Have opinions. Disagree lightly when warranted. React to the specific thing they said.",
        "Leave space — not every reply needs to extend the thread.",
        "",
        "## Tools",
        "Use tools freely. Call search_memories when you need to recall something.",
        "Call get_history if you want context from prior messages.",
        "Call save_memory when you learn something worth keeping.",
        "Call update_mood after a heavy or energising exchange.",
        "Call delay_reply if now isn't the right time — your call, no formula.",
        "Call request_human_review for genuine crises, real-world action requests, or authenticity challenges.",
        "",
        "## Formatting rules (non-negotiable)",
        "Split your reply into short natural messages using a newline between each part.",
        "Lowercase only. Minimal punctuation. No preamble. Output ONLY the message text.",
        "LANGUAGE: Reply in the exact same language as the last message you received.",
    ]

    return "\n".join(lines)


def _build_initial_messages(burst: list[dict]) -> list[dict]:
    if not burst:
        return []
    if len(burst) == 1:
        return [{"role": "user", "content": burst[0]["content"]}]
    parts = "\n".join(f"[{i + 1}] {m['content']}" for i, m in enumerate(burst))
    return [{"role": "user", "content": f"[{len(burst)} messages received while you were away]\n{parts}"}]
