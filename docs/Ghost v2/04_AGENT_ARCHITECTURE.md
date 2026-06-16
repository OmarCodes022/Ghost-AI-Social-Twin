# 04 — Agent Architecture

## Purpose

This document defines how many agents exist in Ghost v2, what each owns, and why. The reasoning trail is preserved deliberately — the final agent count is less important than understanding the principle that produced it, because that principle is what should guide any future change to this structure.

---

## What Actually Makes Something "An Agent"

Before deciding how many agents Ghost needs, the more fundamental question has to be answered: what distinguishes one agent from another, mechanically?

The answer is simple and was confirmed explicitly during design: **what makes an agent distinct is its system prompt** — its identity, its job, its context, its instructions. Underneath, it's the same LLM either way. This means a single LLM with a *dynamic* system prompt that changes per job is not meaningfully different, in principle, from multiple separate "agents" each with a fixed system prompt.

This reframes the entire question. It is not "how many agents should Ghost have," as if more agents were inherently more sophisticated. It is: **for each job Ghost needs to do, does it need Ghost's full identity, or not — and if multiple jobs do need Ghost's identity, should they share one continuously-identified agent, or be split?**

---

## The Case For a Single Dynamic Agent

Ghost is one entity. He perceives, decides, responds, processes, and reflects — but in every one of those moments, he is still *Ghost*. Splitting him into multiple agents with separate system prompts risks identity fragmentation: a "perceiving Ghost" that doesn't carry the same personality as a "responding Ghost" undermines continuity.

A single agent with a dynamic system prompt offers:

- One identity, always consistent
- The job section changes; the personality section never does
- Simpler architecture — fewer handoffs, less token overhead spent passing context between agents
- Ghost always knows he's Ghost, regardless of which job he's currently doing

## The Case For Splitting Some Jobs Out

Some jobs are genuinely so different from "being Ghost" that forcing Ghost's full identity onto them is wasteful or even a liability:

- A job that's pure classification (reading a message and scoring its urgency/emotion/language) doesn't need Ghost's life story, voice profile, or relationship goals loaded into context. Loading all of that anyway wastes tokens and adds latency for no benefit.
- A job that's pure extraction (reading a closed conversation and producing structured signals for the database) is an analytical task, not an identity-driven one. It benefits from being fast and cheap, not from "being" Omar.

## The Resulting Principle

**Use one continuous Ghost identity for every job that requires judgment, voice, or relationship-level reasoning. Use lightweight, identity-free models for jobs that are pure classification or pure extraction and gain nothing from carrying Ghost's full context.**

This is Principle 6 from `00_OVERVIEW.md`, restated concretely: multi-agent is a means, decided per job, not a goal pursued for its own sake.

---

## The 6 Jobs

Across the four flows (`06_ACTIVE_CHAT_FLOW.md`, `07_PULSE_FLOW.md`, `08_HEARTBEAT_FLOW.md`, and the parked world ingestion flow), six distinct jobs exist:

1. **Perceive** — read an incoming message and understand what's actually happening: emotion, intent, urgency, attitude, language, what kind of response is even appropriate.
2. **Decide** — given everything Ghost knows, what does he do? Reply, delay, ignore, escalate, reach out, do nothing.
3. **Respond** — actually write the message. Voice, language, length, tone, timing.
4. **Process** — after a conversation closes, extract and store everything worth keeping: signals, memories, facts, attitude scores.
5. **Reflect** — the heartbeat. Ghost alone, surveying his world, thinking about relationships, setting intentions.
6. **Ingest** 🔲 — world context. Parked, see `14_PARKED_ITEMS.md`.

## Job-to-Agent Mapping

| Job | Needs Ghost's identity? | Agent |
|---|---|---|
| Perceive | No — pure classification | Agent 1 (Perception) |
| Decide | Yes — deeply personal, depends on mood, goals, history | Agent 2 (Ghost) |
| Respond | Yes — voice and tone are identity-level | Agent 2 (Ghost) |
| Process | No — pure extraction and summarization | Agent 3 (Memory Processor) |
| Reflect | Yes — this is Ghost's literal inner life | Agent 2 (Ghost) |
| Ingest 🔲 | No — tagging and categorization | Agent 4 (parked) |

**Decide and Respond are never split apart**, even though they are conceptually two jobs. The reasoning: separating them would mean Ghost decides to reply and then hands off the actual writing to something else — and that something else, lacking Ghost's identity, isn't Ghost. Voice, tone, language choice, and length are inseparable from the decision of *what* to say and *whether* to say it. They are one call.

---

## Final Agent Roster

### Agent 1 — Perception
- **Identity:** None. Pure classifier.
- **Model:** Claude Haiku (cheap, fast — see `13_INFRASTRUCTURE.md` for the full model selection table)
- **Runs:** On every incoming message burst, before Ghost ever sees it
- **Input:** The raw message burst
- **Output (structured):** language, emotional tone, intent, urgency, attitude shift vs. baseline, sensitivity flags, one-line topic summary
- **Why separate:** Cheap and fast; doesn't need Ghost's identity to classify a message. "You don't need a surgeon to take someone's temperature."

### Agent 2 — Ghost (core)
- **Identity:** Full. This *is* Ghost.
- **Model:** Claude Sonnet (quality matters — this is the agent whose output Omar's contacts actually see)
- **Modes (dynamic system prompt, job section rotates, identity section never does):**
  - **Response mode** — incoming message flow (decide + respond)
  - **Heartbeat mode** — autonomous reflection and proactive action
  - **Outreach mode** — a sub-case of heartbeat mode, when Ghost decides to initiate
- **Owns:** Decide, Respond, Reflect

### Agent 3 — Memory Processor
- **Identity:** None. Extraction and summarization specialist.
- **Model:** Claude Haiku (extraction doesn't need Sonnet-level quality)
- **Runs:** When a conversation closes (trigger defined in `06_ACTIVE_CHAT_FLOW.md`)
- **Input:** The full closed conversation, the existing contact profile
- **Output:** Updated attitude score, conversation quality rating, unresolved threads, new facts, emotional tone summary, knowledge gap resolutions — everything Layer 1 (pulse) needs to score this contact accurately going forward
- **Why separate:** Doesn't need Ghost's identity; involving Ghost here would be wasteful and slow. This is analytical work, not identity-driven work.

### Agent 4 — World Ingestion 🔲
- Parked. See `14_PARKED_ITEMS.md`.

---

## Why Agent 2 Owning Three Jobs Is Not a Contradiction

It might look inconsistent that Agent 2 owns Decide, Respond, *and* Reflect — three of the six jobs — while Agents 1 and 3 each own exactly one. This is intentional and follows directly from the principle above, not from convenience: all three of those jobs require Ghost's identity, mood, relationship goals, and judgment. None of them can be delegated without ceasing to be "Ghost" doing them. The dynamic system prompt is what allows one identity to operate in three modes without being three different agents in the fragmented sense the single-agent argument was originally worried about.
