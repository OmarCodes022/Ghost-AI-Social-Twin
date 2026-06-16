# 06 — Active Chat Flow

## Purpose

This document defines the complete, step-by-step path a message takes from arriving on WhatsApp to the conversation eventually closing and being processed into memory. This is the most frequent and most complex flow in the system — everything else exists in service of making this flow good.

This flow owns everything triggered by an incoming message, inside a specific thread, in the moment. It explicitly does **not** own proactive outreach or autonomous reflection — those belong to the heartbeat flow (`08_HEARTBEAT_FLOW.md`). The boundary between the two was deliberately drawn during design:

> **Active chat owns:** everything triggered by an incoming message, inside a specific thread, in the moment — replying, timing the reply, choosing tone, deciding to delay deliberately, playing hard to get in response to a specific message.
>
> **Heartbeat owns:** everything Ghost does alone, with no thread open — proactive outreach, inner-state evolution, relationship monitoring, world awareness, cross-contact pattern recognition, intentions, and conscious silence decisions made *without* a triggering message.

A borderline case worth stating explicitly: if Ghost already saw a message, decided to defer, and is now — during a *later* heartbeat — consciously deciding to let it go permanently unanswered, that final decision belongs to heartbeat, because by that point there is no active triggering message driving it; it has become a deliberate relationship decision rather than a response decision.

---

## Trigger

Someone sends a message to the WhatsApp Business number. Meta sends a webhook POST. API Gateway receives it and invokes `ghost-webhook-receiver`, which returns HTTP 200 immediately — before any processing happens — and pushes the raw payload onto `inbound-message-queue` (SQS). This fire-and-forget pattern is carried forward unchanged from v1: it is the correct architecture for any webhook whose time budget is shorter than the actual processing time, and queuing (rather than a bare async Lambda invoke) ensures the message is never lost if anything downstream is briefly unavailable.

---

## Step 1 — Deduplication

Before any other processing: check the inbound `whatsapp_message_id` against the `messages` table's unique index. If it has already been processed, the pipeline terminates immediately. This is unchanged from v1 and remains correct — it is the first of two protections (the second being the advisory lock used during DB writes) that together make the pipeline effectively idempotent against duplicate webhook deliveries.

## Step 2 — Burst Collection

The pipeline waits a short window (5–10 seconds) and collects every message that arrives in rapid succession from the same contact into a single unit. This is unchanged from v1 and remains correct: it is what allows "yo / u there? / hello??" to be treated and responded to as one coherent message rather than three separate, disjointed replies.

## Step 3 — Agent 1: Perception

The collected burst is sent to Agent 1 (see `04_AGENT_ARCHITECTURE.md`). No Ghost identity is loaded. Output is a structured object:

```json
{
  "language": "french",
  "emotion": "dry",
  "intent": "checking_in",
  "urgency": "low",
  "attitude_shift": -0.1,
  "sensitivity_flags": [],
  "topic_summary": "asking what Ghost is doing this weekend"
}
```

This output becomes part of the context package assembled in the next step. It is also written to `contact_state` immediately (the `attitude_shift` value contributes to that contact's running attitude trend — see `09_DB_SCHEMA.md`), satisfying Principle 4: understanding is captured the moment it's produced, not recomputed later.

## Step 4 — Context Assembly

The pre-assembled (Tier 1, per `02_DELIVERY_MAP.md`) context package is built and injected into the human turn:

- Core identity (system prompt, cached)
- Ghost's inner state (fresh from `ghost_state`)
- The world right now (time, date, calendar)
- Contact profile (`contacts` + `contact_state`)
- Per-person rules (`per_person_rules`)
- Conversation history (recent window as real turns + older summary from `conversations.summary`)
- Timing and life events for this contact (`life_events`)
- Dynamic few-shots, selected by this contact's language and relationship tier (`omar_few_shots`)
- Agent 1's perception output from Step 3

Anything beyond this (deep memories, specific facts not already in the profile, cross-contact information, deep persona content) is **not** included here — it is Tier 2, and Ghost retrieves it himself in the next step if he decides he needs it (see `03_MEMORY_SYSTEM.md`).

## Step 5 — Agent 2 (Ghost) Thinks and Decides

Ghost reasons via an explicit scratchpad (assistant-turn chain-of-thought) before producing any action. He may call the SQL tool or RAG tool at this point if something in the pre-assembled package makes him want more — a name he doesn't recognize, a topic that should trigger a memory check, uncertainty about a fact.

He then resolves to exactly one of three top-level actions:

### A. Reply now
Ghost writes the message himself — voice, language, length, tone are all his to decide, informed by the per-language voice profile and dynamic few-shots already in context. He also reasons explicitly about **timing** before dispatch (full detail in `10_GUARDRAILS_AND_TIMING.md`) — this is not a random delay, it is a reasoned decision ("I'll reply in 20 minutes because this is casual and I've replied instantly to this person too many times lately"), which gets stored as a `time_elapsed` defer condition on the *send*, not on the decision to respond at all.

After dispatch, Ghost also sets a **conversation close condition** (using the same condition vocabulary from `05_CONDITION_SYSTEM.md`) — e.g., `{ "type": "time_elapsed", "minutes": 240 }` for a casual back-and-forth, or 18 hours after something like "see you tomorrow." This condition, once satisfied, is what triggers Agent 3 (Step 9 below).

### B. Conscious defer
Ghost decides not to reply right now. He does **not** pre-write a response. He writes a structured condition (any type from `05_CONDITION_SYSTEM.md`) plus his reasoning into `defer_conditions`, with `status = 'active'`. The contact's `unanswered_message_flag` is set in `contact_state`, but critically — and this was a specific correction made during design — **this does not immediately flag the contact for heartbeat just because a message is sitting unanswered.** Pulse tracks it as a signal that accumulates weight over time (see `07_PULSE_FLOW.md`); it does not jump straight to urgent.

### C. Escalate
Something in the message — flagged by Agent 1's `sensitivity_flags` or recognized by Ghost directly — requires Omar's real judgment: crisis, conflict beyond Ghost's scope, anything emotionally high-stakes. An SNS notification fires to `ghost-telegram-bot` via `escalation-queue`, presenting the situation with Send / Edit / Skip options, exactly as in v1.

## Step 6 — Ghost's Inline Internal Updates (always, regardless of A/B/C above)

This step is distinct from Agent 3 (Step 10) and the distinction matters enough to state explicitly, because it was a direct point of clarification during design:

> **Inline updates (this step)** happen immediately, in the same call, while Ghost is still "in the moment" of the conversation. These are Ghost's **subjective, immediate reactions** — how he feels right now, what he just decided about this relationship, in response to this specific message. Fast, personal, reactive.
>
> **Agent 3 (Step 10)** happens later, only once the entire conversation has closed, and reads the **full conversation as a whole**, not just the triggering message. It produces **objective, retrospective signals** — the attitude trend over the whole exchange, overall conversation quality, the complete list of unresolved threads. Analytical, complete, feeds pulse.

Concretely: in this step, Ghost might update his mood, drop or raise his stance toward this contact, or write a new intention — directly, via the SQL tool, in the same call that produced the reply or defer decision. Neither replaces the other; both are necessary.

## Step 7 — Message Dispatch (if Reply Now)

The reply is pushed onto `outbound-message-queue` (a FIFO queue, partitioned by contact phone number as the message group ID, guaranteeing in-order delivery per contact while still allowing full parallelism across different contacts). `ghost-whatsapp-sender` consumes it: shows a typing indicator, waits the naturally-reasoned delay from Step 5A, then sends.

## Step 8 — Conversation State

The conversation row in `conversations` is marked `open` if this is a new thread, and its `close_condition` field is updated per Step 5A. No formal `arc_state` enumeration (open / flowing / winding_down / dormant) is carried forward from v1 — that system was mostly manual and never worked reliably. In v2, a conversation is simply **open** or **closed**, and the only thing that distinction exists for is deciding whether Agent 3 should fire. Nothing else in the system reads conversation "lifecycle" beyond this binary.

## Step 9 — Pulse Monitors the Close Condition

Every pulse iteration evaluates the conversation's close condition exactly as it evaluates any other condition (`05_CONDITION_SYSTEM.md`). When satisfied, the conversation is marked `closed`, and a message is dropped onto `memory-processing-queue`.

## Step 10 — Agent 3: Memory Processor

Triggered by `memory-processing-queue`. Reads the entire closed conversation. Produces and writes, in one pass:

- Updated attitude score and trend direction/duration
- Conversation quality rating
- Full list of unresolved threads
- New facts worth remembering (written to `memories`, embedded via Voyage-3)
- Emotional tone summary for the conversation
- Resolution of any `contact_knowledge_gaps` that were organically filled during this conversation (see `12_ONBOARDING_CONTACTS.md`)
- Any updated relationship intentions
- Everything `contact_state` needs for pulse to score this contact accurately going forward

This is intentionally decoupled and non-blocking — Ghost has already replied and moved on; memory processing happens whenever Agent 3 gets to it, with no impact on response latency.

---

## Full Flow Summary

```
Webhook fires (200 returned immediately)
        │
        ▼
inbound-message-queue (SQS)
        │
        ▼
Deduplication ──► [if duplicate] STOP
        │
        ▼
Burst collection (5-10s window)
        │
        ▼
perception-output-queue (SQS) ◄── Agent 1: Perception
        │                          (language, emotion, intent, urgency,
        │                           attitude_shift, sensitivity, topic)
        ▼
Context Assembly (Tier 1, automatic)
        │
        ▼
Agent 2: Ghost thinks (scratchpad)
        │   may call SQL/RAG tools (Tier 2, Ghost's own initiative)
        │
        ├── REPLY NOW ──► outbound-message-queue (FIFO) ──► ghost-whatsapp-sender
        │                  + sets conversation close condition
        │
        ├── CONSCIOUS DEFER ──► defer_conditions (status=active)
        │                        + unanswered_message_flag set (not auto-flagged)
        │
        └── ESCALATE ──► escalation-queue ──► SNS ──► ghost-telegram-bot
        │
        ▼
Ghost's inline internal updates (always — mood, stance, intentions via SQL tool)
        │
        ▼
[Pulse evaluates close condition every 1-2 min — see 07_PULSE_FLOW.md]
        │
        ▼
Conversation marked closed ──► memory-processing-queue
        │
        ▼
Agent 3: Memory Processor ──► writes attitude score, quality, unresolved
                                threads, new facts, gap resolutions, intentions
                                to contact_state, memories, conversations,
                                contact_knowledge_gaps
```

This flow connects directly into `07_PULSE_FLOW.md` (which evaluates every condition this flow creates) and `09_DB_SCHEMA.md` (which defines every table this flow reads and writes).
