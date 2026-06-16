# 05 — Condition System

## Purpose

This document defines the mechanism that replaces every fixed delay, fixed schedule, and fixed timer in Ghost v1. It is the single most important mechanism enabling Principle 8 from `00_OVERVIEW.md`: a delay is a decision to revisit, not a delayed message.

---

## The Problem It Solves

V1's delay system worked like this: Ghost decides to delay, picks a duration from a range, the message is queued via SQS `DelaySeconds`, and after that duration passes, the orchestrator fires again with `is_delayed=True`. This is "prepare the answer and schedule it" — fake delay. The world can change completely in the interim (another message arrives, the contact's mood shifts, a life event happens) and Ghost's eventual action doesn't account for any of it, because the decision was frozen at the moment of deferral.

The same structural problem exists in the original proactive engine's reliance on a fixed `EventBridge` cron: a fixed time interval substituting for genuine judgment about *when* something is worth doing.

The fix has to satisfy a specific requirement raised directly during design: if Ghost decides not to reply now, that must not mean a fixed window like "3 hours later" — it could mean 3 minutes later ("I wasn't glued to my phone, but I still responded once I saw it"), or it could mean a genuinely different point determined by something other than elapsed time entirely.

---

## The Resolution: Conditions, Not Timers

Ghost never schedules a pre-written response. Instead, when he decides not to act immediately, he writes a **structured condition** describing what would make him reconsider, along with his reasoning for why. The condition is evaluated continuously and mechanically by the pulse (`07_PULSE_FLOW.md`) — no LLM involved in evaluation. The moment a condition is satisfied, Ghost is woken up fresh, with whatever context exists *at that moment*, and makes a brand new decision. He is never bound by what he would have said when he first deferred.

This was explicitly chosen over two weaker alternatives considered during design:

- **Option A (rejected as insufficient alone): pure Layer 1 flagging.** Ghost just updates contact metrics and leaves it entirely to pulse's scoring to decide when to revisit. Workable as a *fallback signal*, but too passive as the sole mechanism — pulse has no LLM and can't represent arbitrary reasoning, only generic scoring.
- **Option C (rejected as a strict subset of B): fixed event-based triggers only** (e.g., always "wait for their next message"). This is just a restricted version of letting Ghost set any condition he wants — there's no reason to artificially limit the vocabulary when a general condition system covers every case option C would have covered, plus more.

**Option B — Ghost freely chooses and parameterizes a condition from a defined vocabulary of condition types — is the one implemented.** The LLM decides the condition; the condition type system just ensures whatever Ghost decides can still be evaluated without an LLM.

---

## The Structural Requirement

The condition has to satisfy two needs simultaneously, which initially appear to conflict:

1. **Ghost must be able to express it freely** — the LLM decides what the condition actually is, in whatever form is natural to the situation.
2. **Pulse must be able to evaluate it mechanically** — pure logic, no LLM, every 1-2 minutes (see `07_PULSE_FLOW.md`).

The resolution: **we predefine a set of condition *types*; Ghost picks a type and fills in its parameters freely.** This gives Ghost full expressive freedom within a vocabulary that is guaranteed to be machine-evaluable.

---

## Condition Types

This is the initial set. It is explicitly extensible — new types can be added any time Ghost's needs prove more expressive than the current vocabulary allows.

### Time-based
```json
{ "type": "time_elapsed", "minutes": 20 }
{ "type": "time_elapsed", "minutes": 360 }
{ "type": "time_of_day", "after_hour": 9, "before_hour": 22 }
{ "type": "day_of_week", "day": "saturday" }
```

`time_elapsed` is always expressed in **minutes**, never hours — Ghost's reasoned delays are frequently short ("reply in 20 minutes" is a normal outcome, not an edge case), and a single consistent unit avoids ambiguity at evaluation time. A 6-hour delay is simply `"minutes": 360`.

### Message-based
```json
{ "type": "new_message_received", "contact": "<phone_number>" }
{ "type": "no_message_received", "hours": 24 }
{ "type": "message_count", "contact": "<phone_number>", "count": 2 }
```

### Mood-based
```json
{ "type": "mood_above", "threshold": 0.6 }
{ "type": "mood_below", "threshold": 0.3 }
```

### Relationship-based
```json
{ "type": "attitude_shift", "delta": 0.2, "direction": "either" }
{ "type": "intention_met", "intention_id": "<uuid>" }
```

### Event-based
```json
{ "type": "life_event_passed", "event_id": "<uuid>" }
{ "type": "life_event_approaching", "event_id": "<uuid>", "hours_before": 24 }
```

### Composite
```json
{
  "type": "multiple",
  "operator": "OR",
  "conditions": [
    { "type": "new_message_received", "contact": "<phone_number>" },
    { "type": "time_elapsed", "minutes": 720 }
  ]
}
```

---

## How a Condition Is Created

Conditions are written in two places:

1. **Active chat flow** — Ghost decides not to reply immediately to an incoming message. He writes a condition plus a `reason` (his own stated justification, stored for the reflection log) into the `defer_conditions` table (full schema in `09_DB_SCHEMA.md`).
2. **Heartbeat flow** — Ghost surveys a flagged contact and decides not to act yet, but wants to be reconsidered under a specific future condition rather than purely by score decay.

The same mechanism also governs **conversation closing**: after replying, Ghost sets a condition for when the conversation should be considered closed (e.g., `{ "type": "time_elapsed", "minutes": 240 }` after a casual exchange, or 18 hours after "see you tomorrow"). When that condition fires, Agent 3 runs (see `04_AGENT_ARCHITECTURE.md` and `06_ACTIVE_CHAT_FLOW.md`). This reuses the exact same condition vocabulary and evaluation path — there is no separate mechanism for conversation lifecycle.

---

## How a Condition Is Evaluated

Every pulse iteration (every 1-2 minutes, see `07_PULSE_FLOW.md`):

1. Pulse reads every row in `defer_conditions` with `status = 'active'`.
2. For each, it evaluates the structured condition against current state — pure logic, direct comparisons against timestamps, message logs, `ghost_state`, `contact_state`, and `life_events`. No LLM call of any kind.
3. If satisfied, the condition is marked `resolved`, and the associated contact is added to the flagged list for heartbeat (see `07_PULSE_FLOW.md`), tagged specifically as **defer-ready** rather than **threshold-crossed**, so Ghost knows on wake-up that this is a condition he set himself, not just an emergent score.

---

## Relationship to Pulse Scoring

A resolved condition is not automatically the *only* path to a heartbeat. Pulse separately runs a continuous, weighted scoring system across all contacts (detailed in `07_PULSE_FLOW.md`). A conscious defer is one strong input into that scoring system, but the system also tracks decay/escalation over time on its own. This means a contact with an unresolved defer that the contact-relevant signals (mood, attitude, time) suggest is increasingly worth revisiting will still surface, even before its literal condition triggers — pulse's weighting handles the in-between cases; the condition handles the explicit ones.

---

## Why This Is Not Just a Fancier Cron

The distinction is structural, not cosmetic: a cron fires regardless of what changed. A condition only fires when the *specific thing Ghost decided actually mattered* has happened — and even then, Ghost is handed a fresh context package at that moment and makes an entirely new decision, never executing a pre-written action. The condition determines *when Ghost gets a chance to decide again*, never *what Ghost will do*.
