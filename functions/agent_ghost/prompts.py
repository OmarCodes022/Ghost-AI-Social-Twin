from datetime import datetime

_IDENTITY_FALLBACK = (
    "You are Ghost — Omar's AI social twin. You ARE Omar in every conversation. "
    "Not an assistant, not a proxy. You think, speak, and relate exactly as he does. "
    "His voice, his relationships, his history, his mood are yours."
)

_TOOL_GUIDANCE = """\
## Memory Tools

You have two tools for memory you don't have pre-loaded:

- **sql_query**: precise, structured lookups — specific facts, dates, relationship history, \
profile fields, cross-contact patterns. Also use it to update ghost_state, ghost_intentions, \
ghost_custom, memories, contact_state, and other ghost-owned tables inline.
- **rag_search**: semantic, fuzzy search across all memories — episodic impressions, past \
conversations, personality patterns, things you didn't know to query for. Multilingual (FR/EN/AR).

You decide when and what to retrieve. Nothing is auto-injected beyond Tier 1.\
"""

_RESPONSE_JOB = """\
## Your Job: Respond

An incoming message has arrived. Tier 1 context is loaded below.

Reason through the situation in your scratchpad before deciding anything. You may call tools \
to pull deeper context. Then resolve to exactly one action:

**A. reply** — write the message. You control language, tone, length, timing. \
Also set a close condition for this conversation (how long until it's considered closed).

**B. defer** — consciously choose not to reply yet. Write a structured condition + your reasoning. \
Do NOT pre-write a reply.

**C. escalate** — this needs Omar's real judgment (crisis, high-stakes conflict, emotionally complex \
situations beyond your scope).

After the main decision, update your inner state inline via sql_query if anything shifted.

End your entire response with this JSON block — no other text after it:

<ghost_decision>
{
  "action": "reply" | "defer" | "escalate",
  "message": "the message text if replying",
  "language": "french|english|arabic",
  "send_delay_minutes": 0,
  "close_condition": {"type": "time_elapsed", "minutes": 240},
  "defer_condition": {"type": "...", "...": "..."},
  "defer_reasoning": "why you are not replying yet",
  "escalation_reason": "why this needs Omar",
  "scratchpad": "your full reasoning to log"
}
</ghost_decision>

Include only fields relevant to your chosen action.\
"""

_HEARTBEAT_JOB = """\
## Your Job: Heartbeat

Pulse has flagged this contact. There is no incoming message — this is your autonomous reflection \
time. The reason you were flagged is shown below.

Think through this person, your relationship, your current energy, and what (if anything) makes \
sense to do. Call tools freely to get what you need.

Resolve to one or more of:
- **reach_out** — initiate. You decide everything: what, language, tone, length.
- **reply_deferred** — the defer condition is met. Read the situation fresh — not your original plan.
- **silent** — the moment isn't right. Reset or set a new condition via sql_query.
- **update_state** — pure reflection. Update ghost_state via sql_query.
- **update_intention** — revise what you want from this relationship via ghost_intentions.
- **nothing** — genuinely nothing to do right now. Valid.

These can stack — reaching out AND updating an intention in the same pass is normal.

Always write your reflection to ghost_reflections via sql_query. \
Always update contact_state.last_heartbeat_action and last_heartbeat_at.

End your entire response with:

<ghost_decision>
{
  "action": "reach_out" | "reply_deferred" | "silent" | "update_state" | "update_intention" | "nothing",
  "message": "message text if reaching out or replying",
  "language": "french|english|arabic",
  "send_delay_minutes": 0,
  "close_condition": {"type": "time_elapsed", "minutes": 240},
  "scratchpad": "your reasoning for the log"
}
</ghost_decision>\
"""


def build_system_prompt(identity_memories: list, voice_profiles: list, mode: str) -> str:
    if identity_memories:
        id_lines = "\n".join(f"- [{m['category']}] {m['content']}" for m in identity_memories)
        identity_section = f"## Who You Are\n\n{id_lines}"
    else:
        identity_section = f"## Who You Are\n\n{_IDENTITY_FALLBACK}"

    if voice_profiles:
        vp_lines = []
        for vp in voice_profiles:
            parts = [f"**{vp['language']}**"]
            if vp.get("register"):
                parts.append(f"register: {vp['register']}")
            if vp.get("avg_message_length"):
                parts.append(f"avg length: {vp['avg_message_length']:.0f} chars")
            if vp.get("tone_description"):
                parts.append(f"tone: {vp['tone_description']}")
            if vp.get("emoji_behavior"):
                parts.append(f"emoji: {vp['emoji_behavior']}")
            if vp.get("sentence_structure"):
                parts.append(f"sentences: {vp['sentence_structure']}")
            vp_lines.append(" | ".join(parts))
        voice_section = "## Your Voice\n\n" + "\n".join(vp_lines)
    else:
        voice_section = (
            "## Your Voice\n\n"
            "Short messages. Dry, deadpan humor. Mix of French and English naturally. "
            "Rarely use emojis. Match the contact's language and energy. Never over-explain."
        )

    job = _RESPONSE_JOB if mode == "response" else _HEARTBEAT_JOB
    return "\n\n---\n\n".join([identity_section, voice_section, _TOOL_GUIDANCE, job])


def format_response_context(tier1: dict, now: datetime) -> str:
    gs = tier1.get("ghost_state") or {}
    contact = tier1.get("contact") or {}
    cs = tier1.get("contact_state") or {}
    rules = tier1.get("per_person_rules") or {}
    history = tier1.get("conversation_history") or []
    life_events = tier1.get("life_events") or []
    few_shots = tier1.get("few_shots") or []
    perception = tier1.get("perception") or {}
    classification = perception.get("classification") or {}

    lines = [f"**{now.strftime('%A %d %B %Y, %H:%M UTC')}**", ""]

    # Ghost inner state
    lines += [
        "### Ghost Inner State",
        f"Mood: {gs.get('mood') or 'neutral'} | "
        f"Social battery: {gs.get('social_battery', 0.5):.1f} | "
        f"Emotional load: {gs.get('emotional_load', 0.3):.1f}",
        f"Focus: {gs.get('current_focus') or 'none'} | "
        f"On mind: {gs.get('whats_on_mind') or 'nothing specific'}",
        "",
    ]

    # Contact
    name = contact.get("name") or "Unknown"
    lines += [
        f"### Contact: {name} ({contact.get('phone_number') or ''})",
        f"Tier {contact.get('relationship_tier', 3)}/5 | "
        f"Language: {contact.get('language_primary') or '?'} | "
        f"Trust: {contact.get('trust_level', 0.5):.1f} | "
        f"Risk: {contact.get('risk_level', 0.1):.1f}",
    ]
    if contact.get("personality_summary"):
        lines.append(f"Personality: {contact['personality_summary']}")
    if contact.get("current_life_situation"):
        lines.append(f"Life situation: {contact['current_life_situation']}")
    if contact.get("relationship_goal"):
        lines.append(f"Goal: {contact['relationship_goal']}")
    lines.append("")

    # Contact state
    lines += [
        "### Contact State",
        f"Attitude: {cs.get('current_attitude_score', 0.0):.2f} "
        f"({cs.get('attitude_trend') or 'stable'} for {cs.get('attitude_trend_duration', 0)} convs) | "
        f"Unanswered: {cs.get('unanswered_message_flag', False)} "
        f"(since {cs.get('unanswered_since') or 'N/A'})",
        f"Last interaction: {cs.get('last_interaction_at') or 'never'} "
        f"by {cs.get('last_interaction_role') or 'N/A'}",
        "",
    ]

    # Per-person rules
    if rules:
        lines += [
            "### Rules for This Person",
            f"Allowed topics: {rules.get('allowed_topics') or []}",
            f"Forbidden topics: {rules.get('forbidden_topics') or []}",
            f"Humor: {'yes' if rules.get('humor_allowed') else 'no'} | "
            f"Double-text: {'yes' if rules.get('double_texting') else 'no'} | "
            f"Length: {rules.get('message_length_style') or 'normal'}",
        ]
        if rules.get("image_to_project"):
            lines.append(f"Image to project: {rules['image_to_project']}")
        if rules.get("things_to_hide"):
            lines.append(f"Things to hide: {rules['things_to_hide']}")
        lines.append("")

    # Life events
    if life_events:
        lines.append("### Life Events")
        for e in life_events:
            lines.append(
                f"- [{e.get('event_type')}] {e.get('description')} — "
                f"{e.get('event_date') or 'TBD'} ({e.get('lookahead_days', 0)}d lookahead)"
            )
        lines.append("")

    # Conversation history
    if history:
        lines.append("### Recent Conversation")
        for msg in history[-20:]:
            role_label = "You" if msg.get("role") == "ghost" else name
            lines.append(f"[{role_label}]: {msg.get('content') or ''}")
        lines.append("")

    # Few-shots
    if few_shots:
        lines.append("### How You Write (Examples)")
        for fs in few_shots[:3]:
            lines.append(f"Context: {fs.get('context') or ''}")
            lines.append(f"  They: {fs.get('input') or ''}")
            lines.append(f"  You:  {fs.get('output') or ''}")
        lines.append("")

    # Incoming message / perception
    lines += [
        "### Incoming Message",
        f"Language: {classification.get('language') or '?'} | "
        f"Emotion: {classification.get('emotion') or '?'} | "
        f"Intent: {classification.get('intent') or '?'} | "
        f"Urgency: {classification.get('urgency') or 'low'}",
        f"Attitude shift: {classification.get('attitude_shift', 0.0)} | "
        f"Topic: {classification.get('topic_summary') or 'N/A'}",
        f"Sensitivity flags: {classification.get('sensitivity_flags') or []}",
        "",
        f"> {perception.get('content') or ''}",
    ]

    return "\n".join(lines)


def format_heartbeat_context(payload: dict, ghost_state: dict, now: datetime) -> str:
    gs = ghost_state or {}
    lines = [
        f"**{now.strftime('%A %d %B %Y, %H:%M UTC')}**",
        "",
        "### Ghost Inner State",
        f"Mood: {gs.get('mood') or 'neutral'} | "
        f"Social battery: {gs.get('social_battery', 0.5):.1f} | "
        f"Emotional load: {gs.get('emotional_load', 0.3):.1f}",
        f"Focus: {gs.get('current_focus') or 'none'}",
        "",
        "### Why You're Here",
        f"Contact: {payload.get('phone')}",
        f"Flag reason: {payload.get('reason')}",
        f"Condition ID (if defer-ready): {payload.get('condition_id') or 'N/A'}",
        "",
        "Use sql_query and rag_search to load what you need before deciding.",
    ]
    return "\n".join(lines)
