# 10 — Guardrails & Timing Intelligence

## Purpose

This document separates two things that are easy to conflate: **guardrails** (hard, code-level rules Ghost cannot override regardless of his reasoning) and **timing intelligence** (Ghost's own reasoned judgment about *when* to act, which is deliberately *not* hardcoded). The boundary matters because the entire architecture depends on minimizing the first category and maximizing the second — guardrails exist only where a wrong decision would be unacceptable, never as a substitute for genuine judgment.

A broader set of potential guardrails (content restrictions, frequency caps, sensitivity escalation) was discussed during design and intentionally deferred — locked in as placeholders to expand later — in favor of focusing v2's initial build on the two guardrails judged non-negotiable from day one: **language** and **time**.

---

## Guardrails (Hard Rules)

### Language

- Ghost speaks **only** French, English, and Arabic — the three languages Omar actually speaks fluently. No other language is ever produced, regardless of what language a contact writes in or what the model might otherwise be capable of generating.
- Ghost replies in the **contact's primary language** by default, as recorded in `contacts.language_primary`.
- Ghost only switches language mid-conversation if the **contact switches first** — Ghost never initiates a language switch unprompted.
- For outreach (heartbeat-initiated messages), Ghost always uses the contact's stored primary language — never defaults to English as a fallback.
- Agent 1 (Perception) detects the language of every incoming message explicitly (`06_ACTIVE_CHAT_FLOW.md`, Step 3); this detection is what allows Ghost's reply-language rule to be enforced reliably rather than inferred loosely by Ghost mid-generation.

This directly fixes a concrete v1 failure: v1 had no language discipline at all, and separately, its RAG system always searched in English regardless of the contact's actual language (see `03_MEMORY_SYSTEM.md` for the embedding-level fix to that specific issue).

### Time

- Ghost does not **initiate** outreach during a window considered too late or too early — this window is not a single fixed pair of hours; it is computed dynamically per contact, based on:
  - Omar's own timezone and typical patterns
  - The specific contact's timezone, if different
  - The contact's own known activity patterns (`contact_state` and behavioral history — some people are reliably active late at night, and the guardrail should account for that rather than applying one blanket cutoff to everyone)
- **This guardrail applies only to outreach** — Ghost initiating a conversation via the heartbeat flow. It does **not** apply to replying. If a contact messages Ghost at 2am, that contact is self-evidently awake, and Ghost is free to reply if a reply is otherwise warranted. The guardrail exists to stop Ghost from being the one who breaks the silence at a bad hour, not to stop him from responding to someone who already has.
- Enforced at the **pulse level** (`07_PULSE_FLOW.md`, Step 5) as a hard filter applied before any contact is added to the flagged list for heartbeat — never left to the LLM's judgment to "remember" not to message late at night. This is precisely the kind of rule guardrails exist for: not a matter of taste or context-sensitivity, but a rule that must never be violated by a bad inference.

### Everything else — placeholder

Content restrictions, hard frequency caps, and other previously-discussed guardrail categories (escalation cooldowns, risk-based caution for low-trust contacts, image-management enforcement) remain conceptually identified but explicitly deprioritized for the initial build. They can be added to this document and to the pulse guardrail-filter step (`07_PULSE_FLOW.md`, Step 5) at any time without altering the rest of the architecture — the guardrail layer is designed to be additive.

---

## Timing Intelligence (Ghost's Judgment, Not a Rule)

This is the direct fix for a v1 failure that was distinct from the cron problem: even with a working delay *mechanism*, v1's delay was always a value pulled from a fixed range, with no actual reasoning behind the number. The output looked intentional but wasn't.

In v2, timing is never an input Ghost selects from a range — it is a **byproduct of reasoning** Ghost does anyway, as part of deciding how to respond.

### Timing for replies (active chat)

Before dispatching a reply, Ghost reasons about:

- What time it currently is for this specific contact
- Whether anything is known about this contact's current state (at work, in class, generally busy at this hour)
- The relationship tier — closer contacts generally warrant faster replies, but this is a tendency Ghost weighs, not a rule he follows blindly
- Ghost's own relationship goal for this contact (`per_person_rules.relationship_goal` / `ghost_intentions`) — a deliberate "playing hard to get" stance might call for a slower reply even when nothing else would suggest one
- The tone and urgency of the incoming message, per Agent 1's classification — genuine urgency overrides a slower default
- Ghost's own current social battery (`ghost_state`) — low energy naturally produces slower responses without needing to be told to
- How quickly Ghost has been replying to this specific contact recently — a pattern of instant replies is itself a signal that slowing down would feel more natural going forward

The output of this reasoning is a stated delay with a stated reason ("I'll reply in 20 minutes — this is casual and I've been replying too fast to this person lately"), which becomes a `time_elapsed` defer condition exactly as described in `05_CONDITION_SYSTEM.md`. The duration is never picked from a range; it falls out of the reasoning that produced it.

### Timing for outreach (heartbeat)

When Ghost is considering initiating contact, the same kind of reasoning applies, with different inputs:

- Time of day and day of week for the specific contact
- Their known activity patterns
- Their current life situation — Ghost does not reach out the morning of someone's exam, for instance, because that fact is present in context (`life_events`), not because of a rule saying "don't message during exams"
- Ghost's own energy level — low battery naturally produces lighter or absent outreach

### The core distinction from v1

| | V1 | V2 |
|---|---|---|
| Delay mechanism | A tool call with a duration pulled from a fixed range | A condition Ghost writes, derived from reasoning |
| What decides the duration | A configured range | Ghost's own stated reasoning, every time |
| Proactive cadence | Fixed `EventBridge` cron, every 2 hours | Continuous pulse scoring + Ghost's own judgment at heartbeat time |
| Result | Mechanically regular, emotionally flat | Variable, explainable, grounded in actual context |

Both guardrails (language, time-of-day-for-outreach) and timing intelligence (delay reasoning, outreach timing judgment) work together: guardrails set the absolute boundaries within which Ghost operates; timing intelligence is everything Ghost does freely *inside* those boundaries.
