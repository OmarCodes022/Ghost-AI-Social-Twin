# 07 — Pulse Flow (Layer 1)

## Purpose

Pulse is the nervous system of Ghost. It is pure logic — no LLM call of any kind — and its only job is to read signals that were already computed elsewhere (by an LLM, at the moment understanding was available, per Principle 4) and decide whether anything currently warrants waking Ghost up for a heartbeat (Layer 2, `08_HEARTBEAT_FLOW.md`).

Pulse never tries to *understand* anything. It only reads and scores.

---

## Why Pulse Exists As a Separate Layer

This directly replaces v1's `EventBridge` cron (`ghost-proactive-engine`, firing every 2 hours regardless of context). The fundamental flaw there was that a fixed interval substituted for judgment. Pulse fixes this by being cheap enough to run *very* frequently — eliminating the need for any fixed interval to ever feel necessary — while remaining too unintelligent on its own to make any actual decision. All it can do is notice that something *might* be worth Ghost's attention and request a heartbeat. Ghost is always the one who decides what, if anything, happens next.

---

## Frequency

**Every 1–2 minutes.** This was a deliberate correction made during design: an earlier draft proposed 10–15 minute intervals to keep cost down, but this was rejected — DB reads and pure logic are cheap enough that frequency is not a meaningful cost driver. Running pulse every 1-2 minutes instead of every 10-15 makes a real difference in how natural Ghost feels: a contact Ghost consciously deferred replying to might be revisited 3 minutes later ("I wasn't glued to my phone, but I still responded once I saw it") rather than only ever in fixed 15-minute increments.

## Implementation

A **self-perpetuating SQS loop**, not `EventBridge`. A Lambda processes a pulse cycle, then re-enqueues itself onto `pulse-queue` with a delay of 60–120 seconds (SQS `DelaySeconds`). This was chosen over `EventBridge` for this specific job because:

- No minimum schedule resolution friction
- Self-healing — if the Lambda fails mid-cycle, the message becomes visible again and naturally retries, with no separate dead-letter handling needed for "the schedule stopped"
- Cost profile is effectively identical to `EventBridge` at this volume (well within SQS and Lambda free tiers), so there is no cost tradeoff in choosing the more resilient option

`EventBridge` is reserved in this architecture for things that genuinely need a true calendar-based schedule, such as the parked world ingestion flow (`14_PARKED_ITEMS.md`).

---

## What Pulse Reads, Every Cycle

A full, accurate read — not a cheap, pre-summarized shortcut. This was also a specific correction made during design: an earlier draft proposed maintaining a single pre-computed "score row" per contact to minimize query load, but this was rejected on the grounds that DB reads are not the expensive resource here; understanding is. Pulse always reads the real, current state of every contact directly.

**Step 1 — Global/world state**, read once per cycle, not per contact:
- Current time and day
- Omar's calendar — any active busy blocks right now
- Ghost's current inner state (`ghost_state`) — social battery, mood
- Any active world-relevant events 🔲 (parked)

This produces the global filter used in Step 5 below — for example, if it's the middle of the night, nothing gets flagged for *outreach* regardless of any contact's score (replying to an already-incoming message is unaffected; this filter only applies to Ghost-initiated action).

**Step 2 — Every contact's current signals**, one full read across all contacts:
- Last interaction timestamp and who sent last (`contact_state`, `messages`)
- Baseline communication frequency for this contact (`contact_state.baseline_frequency`)
- Current attitude score and trend direction/duration (`contact_state`)
- Open unanswered-message flag, and any active conscious defer condition (`contact_state`, `defer_conditions`)
- Active Ghost intentions for this contact (`ghost_intentions`)
- Upcoming life events within the lookahead window (`life_events`)
- World relevance tags matched against this contact's known interests 🔲 (parked)
- Current conversation state — open or closed (`conversations`)
- The last heartbeat action taken for this contact, and when (`contact_state.last_heartbeat_action`, `last_heartbeat_at`)

---

## Step 3 — Evaluate Every Active Condition

For every row in `defer_conditions` with `status = 'active'`, and for every open conversation's `close_condition`: evaluate mechanically against the state read in Steps 1–2 (full condition type reference in `05_CONDITION_SYSTEM.md`). No LLM call.

- Condition met → for a defer, mark `resolved` and add the contact to the flagged list as **defer-ready**. For a conversation close condition, mark the conversation `closed` and enqueue it onto `memory-processing-queue` (this is the trigger for Agent 3, detailed in `06_ACTIVE_CHAT_FLOW.md`).
- Condition not met → no action this cycle.

---

## Step 4 — Continuous Weighted Scoring

This is the most important refinement made during design, and it replaces an earlier, simpler binary version of pulse (threshold met / not met). The corrected model: **every signal contributes a weight to a continuously evolving score, every single cycle** — not just at the moment a condition technically resolves.

Concretely, this means a conscious defer with a reason like "reply when my mood improves" does not wait silently until mood crosses some fixed line and then instantly fire. Instead, on every pulse cycle:

- Time elapsed since the defer contributes a weight, increasing gradually
- Current mood relative to the defer's stated condition contributes a weight
- The contact's attitude trend since the defer contributes a weight
- Time of day contributes a weight (favoring cycles where outreach would actually be appropriate)
- Recency delta versus this contact's baseline frequency contributes a weight
- Any upcoming life event contributes a weight
- Active Ghost intentions for this contact contribute a weight
- World relevance 🔲 (parked) contributes a weight when available

The contact's `pulse_score` in `contact_state` is updated every cycle as these weights accumulate. This means a contact is never flagged at an arbitrary, badly-timed instant just because one condition technically resolved — the full picture has to accumulate enough weight, and the system is pure math throughout, no LLM required for any of it.

**Weights and exact ratios are intentionally left as a tunable parameter set, not fixed in this document.** They should be implemented as configuration, not hardcoded constants, so they can be adjusted post-launch based on observed behavior without a code change.

## Step 5 — Apply Global Guardrails

Before anything is added to the flagged list, hard code-level filters are applied (full detail in `10_GUARDRAILS_AND_TIMING.md`):

- **Time-of-day guardrail** — no contact is flagged for *outreach* during a window considered too late/early for either Omar or the specific contact, based on known timezones and activity patterns. (This does not block replying to something already incoming — only Ghost-initiated outreach.)
- **Minimum spacing between heartbeat actions per contact** — a contact cannot be flagged again within a short window of their last heartbeat action unless the accumulated score is high enough to indicate genuine urgency.
- **Escalation cooldown** — a contact that was just escalated isn't immediately re-flagged for an unrelated reason.

These are deterministic code rules. They are never something the LLM is asked to judge or can override — guardrails exist specifically so the system never has to rely on the LLM remembering to behave safely.

## Step 6 — Compile the Flagged List

Two categories, kept distinct so Ghost knows on wake-up which kind of situation he's looking at:

- **Defer-ready** — a condition Ghost explicitly set has just resolved
- **Threshold-crossed** — the continuous weighted score has crossed the configured threshold without any single explicit condition resolving

## Step 7 — Trigger or Sleep

- **Flagged list empty** → pulse writes its own next-cycle timestamp and re-enqueues itself. Nothing else happens. Ghost remains genuinely at rest — this is a valid and expected outcome, not a failure mode.
- **Flagged list non-empty** → for **each** flagged contact, a separate message is pushed onto `heartbeat-queue` (one invocation per contact — see `08_HEARTBEAT_FLOW.md` for why heartbeat is per-contact rather than a single holistic survey call). `heartbeat-queue` allows controlled concurrency, so if many contacts are flagged simultaneously, heartbeats are processed at a deliberate, bounded rate rather than firing all at once.

## Step 8 — Update Pulse Metadata

Every cycle writes:
- Last pulse run timestamp
- Updated `pulse_score` per contact
- Any conditions evaluated and their resulting status
- Whether any heartbeats were triggered this cycle, and for which contacts

---

## Full Cycle Summary

```
SQS pulse-queue message arrives (self re-enqueued every 60-120s)
        │
        ▼
Read global/world state (time, calendar, ghost_state)
        │
        ▼
Read every contact's full current state (contacts, contact_state,
defer_conditions, ghost_intentions, life_events, conversations)
        │
        ▼
Evaluate every active defer_condition + every open conversation's
close_condition  ──► [met] mark resolved/closed, route accordingly
        │
        ▼
Update continuous weighted pulse_score for every contact
(recency, attitude trend, open threads, life events, intentions,
world relevance, time-of-day appropriateness)
        │
        ▼
Apply global guardrails (time-of-day, action spacing, escalation cooldown)
        │
        ▼
Compile flagged list: defer-ready + threshold-crossed
        │
        ├── empty ──► write next-cycle timestamp, re-enqueue self, sleep
        │
        └── non-empty ──► one heartbeat-queue message PER flagged contact
        │
        ▼
Write pulse metadata, re-enqueue self
```

This flow is the sole consumer of every condition created in `05_CONDITION_SYSTEM.md` and the sole producer of heartbeat triggers consumed in `08_HEARTBEAT_FLOW.md`.
