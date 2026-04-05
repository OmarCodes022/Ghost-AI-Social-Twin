"""Telegram dev debug block — sends a trace summary after every agent loop run."""
import json
import logging

import requests

from ssm import get_parameter

logger = logging.getLogger(__name__)

_TOOL_EMOJI = {
    "search_memories": "🔍",
    "get_history": "📖",
    "save_memory": "💾",
    "get_contact_profile": "👤",
    "update_contact_profile": "✏️",
    "get_mood_state": "🌡",
    "update_mood": "💭",
    "delay_reply": "⏱",
    "request_human_review": "🚨",
    "update_conversation_arc": "🔄",
}


def _esc(text: str) -> str:
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def _format_tool_input(tool: str, inp: dict) -> str:
    if tool == "search_memories":
        return f'"{str(inp.get("query", ""))[:40]}"'
    if tool == "get_history":
        return f'limit={inp.get("limit", 20)}'
    if tool == "save_memory":
        return f'"{str(inp.get("content", ""))[:35]}…", {inp.get("category")}'
    if tool == "update_contact_profile":
        return f'{inp.get("field")}="{inp.get("value")}"'
    if tool == "update_mood":
        return f'{inp.get("aspect")}={inp.get("value")}'
    if tool == "update_conversation_arc":
        return f'→ {inp.get("state")}'
    if tool == "delay_reply":
        return f'{inp.get("seconds")}s'
    if tool == "request_human_review":
        return f'"{str(inp.get("reason", ""))[:40]}"'
    return ""


def send_dev_debug(env: str, contact, inbound_message: str, ghost_state, result: dict, burst: list, escalated: bool) -> None:
    try:
        token = get_parameter(f"/ghost/{env}/telegram/bot_token")
        chat_id = get_parameter(f"/ghost/{env}/telegram/chat_id")

        contact_label = contact.name or contact.phone_number
        tool_calls = result.get("tool_calls", [])
        in_tok = result.get("input_tokens", 0)
        out_tok = result.get("output_tokens", 0)
        iters = result.get("iterations", 0)

        trace_lines = []
        errors = []
        for tc in tool_calls:
            emoji = _TOOL_EMOJI.get(tc["tool"], "🔧")
            inp_str = _esc(_format_tool_input(tc["tool"], tc.get("input", {})))
            out_str = _esc(tc.get("output", ""))
            if tc.get("error"):
                errors.append(f'{tc["tool"]}: {_esc(tc["error"])}')
            trace_lines.append(f"  {emoji} `{_esc(tc['tool'])}`\\({inp_str}\\) → {out_str}")

        trace_block = (
            f"🔧 *Trace* \\({len(tool_calls)} tool{'s' if len(tool_calls) != 1 else ''}, {iters} call{'s' if iters != 1 else ''}\\)\n"
            + "\n".join(trace_lines) + "\n\n"
        ) if trace_lines else "🔧 *Trace:* no tools called\n\n"

        error_block = "❌ *Errors:* " + " \\| ".join(_esc(e) for e in errors) + "\n\n" if errors else ""
        burst_line = f"📨 *Burst:* {len(burst)} messages\n\n" if len(burst) > 1 else ""

        if result["action"] == "delay":
            outcome = f"⏱ *Delayed:* {result['seconds']}s — _{_esc(result['reason'])}_"
        elif escalated:
            outcome = f"🚨 *Escalated:* _{_esc(result['reason'])}_"
        else:
            preview = _esc(result.get("reply", "")[:120].replace("\n", " / "))
            outcome = f"💬 *Sent:* _{preview}_"

        text = (
            f"🔍 *\\[DEV\\] Ghost*\n\n"
            f"*From:* {_esc(contact_label)} \\(`{contact.phone_number}`\\)\n"
            f"*Message:* _{_esc(inbound_message[:100])}_\n\n"
            f"{burst_line}"
            f"{trace_block}"
            f"{error_block}"
            f"📊 `{in_tok} in \\+ {out_tok} out tokens`\n\n"
            f"😶 `energy={ghost_state.energy:.2f} battery={ghost_state.social_battery:.2f} "
            f"load={ghost_state.emotional_load:.2f} avail={ghost_state.availability}`\n\n"
            f"{outcome}"
        )

        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "MarkdownV2"},
            timeout=5,
        )
    except Exception as exc:
        logger.warning(json.dumps({"event": "dev_debug_failed", "error": str(exc)}))
