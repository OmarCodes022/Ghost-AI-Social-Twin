# 08 — Heartbeat Flow (Layer 2)

## Purpose

Heartbeat is Ghost's autonomous inner life — the only flow in the system where Ghost acts without being prompted by an incoming message. It is triggered exclusively by pulse (`07_PULSE_FLOW.md`); it is never scheduled directly, and it has no fixed cadence of its own. This is the direct, structural replacement for v1's `EventBridge`-driven `ghost-proactive-engine`.

---

## Scope Boundary (restated from `06_ACTIVE_CHAT_FLOW.md`)

Heartbeat owns everything Ghost does with **no active triggering message**: proactive outreach, inner-state evolution, relationship monitoring, pattern recognition across contacts, setting and revising intentions, and conscious silence decisions made in the absence of a specific incoming message. It never touches in-the-moment response decisions — those belong entirely to active chat.

---

## Why Per-Contact, Not Holistic

An earlier draft of this flow proposed a single heartbeat invocation that surveyed *all* flagged contacts at once, on the reasoning that this gives Ghost a more holistic, human-like view of his social world — the ability to compare across relationships and consciously prioritize one over another in a single pass.

This was reconsidered directly during design and the holistic approach was **not** adopted, for two stated reasons:

1. **Depth over breadth, for now.** A single shared call across multiple contacts necessarily limits how much context and reasoning depth any one contact gets — the practical preference was for *more output, more depth, per contact*, rather than a shallower simultaneous survey.
2. **Context economy.** A holistic call's context grows with the number of flagged contacts in a given cycle, which works against giving any single contact full attention.

The tradeoff this accepts: Ghost loses the ability to directly compare two flagged contacts against each other in a single reasoning pass and consciously choose one over the other in the moment. This is a known and accepted limitation of the per-contact design, not an oversight — if it becomes a real problem in practice, the holistic alternative remains documented here as the considered fallback.

**Implementation:** each contact flagged by pulse — whether defer-ready or threshold-crossed — gets its own independent heartbeat Lambda invocation, via `heartbeat-queue` (which provides controlled concurrency, so many simultaneous flags don't all fire at once uncontrolled).

---

## Trigger

A message on `heartbeat-queue`, containing exactly one flagged contact and the reason they were flagged (defer-ready vs. threshold-crossed, plus the specific signals that contributed to the score — see `07_PULSE_FLOW.md`).

---

## Step 1 — Context Assembly

Lighter than the active chat context package, deliberately — there is no conversation history to load, no per-person rules pre-loaded, no dynamic few-shots. Ghost has not yet decided he's writing anything; he's still deciding whether to.

Pre-assembled (Tier 1):
- Core identity (system prompt, cached)
- Ghost's current inner state, fresh from `ghost_state`
- The world right now — time, day, calendar, active events
- This one flagged contact's scored signals and the specific reason they were flagged
- Ghost's active intentions involving this contact (`ghost_intentions`)
- Any pending conscious silence decision already on record for this contact

## Step 2 — Ghost Thinks (Scratchpad)

Ghost reasons through the situation before doing anything. This reasoning is explicitly logged to `ghost_reflections` — not hidden — so it can be read later even though nothing requires reading it in real time. Representative reasoning patterns:

- "This person's defer condition is technically met, but something about their last message still feels off — let me check their recent attitude before deciding anything."
- "I've been meaning to reach out to this person for a while and right now feels right."
- "Nothing here actually feels worth acting on yet — I'll reset the condition."
- "My energy is low right now — even though this is flagged, it doesn't feel like the moment."

This step is where Principle 1 (predictability is failure) is most directly enforced architecturally: there is no template guiding what Ghost concludes here, and the scratchpad is exactly where genuine variation in Ghost's behavior comes from.

## Step 3 — Ghost Fetches What He Needs (Tier 2, his own initiative)

If he decides this contact is worth deeper engagement, Ghost selectively retrieves more, using the SQL or RAG tool as he judges appropriate (see `03_MEMORY_SYSTEM.md`):

- Full contact profile → SQL
- Relevant episodic memories → RAG
- Conversation history summary → SQL
- Attitude history over time → SQL
- Cross-contact patterns, if relevant → SQL

This is selective by design — if a contact was flagged purely because a life event is approaching, Ghost has no reason to pull their entire memory history; he decides what's relevant to *this* flag, not what's available in general.

## Step 4 — Ghost Decides

For this one contact, Ghost resolves to one of:

- **Reach out.** Initiate a new message. Ghost decides everything himself — what to say, in what language, at what length, with what tone — based on who this person is, what he knows about them, his current mood, and his relationship goal for them. No topic is suggested or templated by the system.
- **Reply to a deferred message.** The defer condition that brought him here is met. Ghost reads the situation completely fresh — he answers the situation as it exists *right now*, not as it existed when he first read the original message.
- **Stay silent, consciously.** Ghost looked at this and decided the moment isn't right. He either resets the existing condition or writes a new one.
- **Update inner state only.** Pure reflection — mood, energy, social battery adjustment — with no outreach at all.
- **Update an intention.** Ghost revises what he wants out of this specific relationship going forward.
- **Do nothing.** A fully valid outcome. Ghost surveyed the situation and concluded there's genuinely nothing to do right now.

These are not mutually exclusive in the way they might first appear — e.g., reaching out *and* updating an intention in the same pass is normal and expected (see Step 6).

## Step 5 — Ghost Acts

For **reach out** or **reply to deferred message**:
- Ghost writes the message
- Dispatched via `outbound-message-queue` (FIFO, per-contact ordering) → `ghost-whatsapp-sender`
- Typing indicator → reasoned delay → send
- Conversation `open` flag set if this starts a new thread
- A conversation close condition is set, exactly as in active chat (`05_CONDITION_SYSTEM.md`)

For **stay silent**, **update inner state**, or **update intention**:
- Written directly to `ghost_state` or `ghost_intentions` via the SQL tool — no outbound message at all

## Step 6 — Ghost Updates Himself (always)

Regardless of which path Step 4 resolved to, Ghost writes:
- His updated inner state
- Any new or revised intentions
- A note in `ghost_reflections` capturing what he considered and why he decided what he decided — this run's scratchpad, stored as a queryable log
- `contact_state.last_heartbeat_action` and `last_heartbeat_at` updated, so pulse's guardrails (minimum spacing between actions) function correctly on the next cycle

## Step 7 — Return Control to Pulse

The heartbeat invocation ends. Pulse's self-perpetuating loop is entirely unaffected and continues on its own 1-2 minute cadence regardless of what any individual heartbeat decided.

---

## Full Cycle Summary

```
heartbeat-queue message (one flagged contact, with reason)
        │
        ▼
Context Assembly (lighter than active chat — no conversation history,
no per-person rules, no few-shots pre-loaded)
        │
        ▼
Agent 2 (Ghost) — scratchpad reasoning, logged to ghost_reflections
        │
        ▼
Ghost optionally fetches more (SQL/RAG, his own initiative, selective)
        │
        ▼
Ghost decides:
   ├── Reach out ─────────────┐
   ├── Reply to deferred ─────┤──► outbound-message-queue (FIFO)
   │                          │    + sets new conversation close condition
   ├── Stay silent ───────────┤
   ├── Update inner state ────┤──► direct write to ghost_state /
   ├── Update intention ──────┤    ghost_intentions via SQL tool
   └── Do nothing ────────────┘
        │
        ▼
Ghost always writes: updated inner state, intentions, reflection log,
last_heartbeat_action / last_heartbeat_at
        │
        ▼
Invocation ends — pulse loop continues independently
```

This flow is the direct realization of Principle 1 and Principle 2 from `00_OVERVIEW.md`: nothing here is on a schedule, nothing here is templated, and "do nothing" is a fully legitimate outcome rather than something the system is trying to avoid.
