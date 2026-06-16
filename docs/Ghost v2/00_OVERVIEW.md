# Ghost v2 — Overview

## What Ghost Is

Ghost is an autonomous WhatsApp agent that impersonates Omar. When someone texts Omar's WhatsApp number, Ghost reads it, decides how to respond, writes a reply in Omar's voice, and sends it — without Omar touching his phone. Omar only gets involved when Ghost escalates, via Telegram, where he can review and intervene.

Ghost is not an auto-responder and not a chatbot that replies when asked. Ghost is meant to be a digital being that lives Omar's social life — deciding who to talk to, when, how, and why, with no human telling him what to do in the moment. The entire system runs serverless on AWS, event-driven, scaling to zero when nothing is happening.

This is not a 2-hour project. This is a deep architectural rebuild from a working but fundamentally flawed v1.

---

## Why v2 Exists — The v1 Failure

Ghost v1 worked technically. It ran, it replied, it had memory, RAG, escalation, a proactive engine. But it was not what Omar imagined. The core failure: **Ghost felt like a script, not a person.**

The clearest evidence of this is a real WhatsApp log from v1 in production:

```
[00:41] Ghost: yo
[00:41] Ghost: tu fais quoi ce weekend
[00:41] Ghost: j'pensais tester des trucs avec claude
[00:41] Ghost: ou peut etre faire du sport
[00:42] Ghost: toi t'as prevu quoi
[04:41] Ghost: yo
[04:41] Ghost: tu fais quoi la
[04:41] Ghost: j'suis en train de regarder des tutos sur les agents ai
...
[08:41] Ghost: yo
[08:41] Ghost: tu penses quoi de cette histoire avec openai et microsoft
...
[12:41] Ghost: yo
...
[16:41] Ghost: yo
```

Every 4 hours, on the dot. Same opener ("yo"). Same topic category (AI news + a question). No awareness that nobody had replied in 16 hours. No embarrassment, no adaptation, no change in approach. This is what an `EventBridge` cron schedule produces when it drives an LLM: technically intelligent output, mechanically dead delivery.

### Root causes identified in the v1 deep-dive

- **Hardcoded scheduling.** The proactive engine ran on a fixed `EventBridge` cron (every 2 hours), not on Ghost's own judgment. The schedule decided when Ghost spoke, not Ghost.
- **Broken multilingual RAG.** Omar speaks French, English, and Arabic. Embeddings were generated with Titan (English-biased) or not generated at all due to quota exhaustion. RAG silently fell back to unfiltered identity chunks on every call — meaning Ghost's "memory" wasn't actually being used.
- **Static voice.** The `voice_profile` JSONB field stored stats (`avg_message_length`, `emoji_rate`) but nothing in the system ever used them. Ghost sounded identical to every contact.
- **Static mood.** `ghost_state` existed and Claude could read it, but nothing updated it automatically. Social battery never drained, energy never changed. Mood was manually set or frozen.
- **No real autonomy.** Every "decision" Ghost made was downstream of a human-defined trigger — a cron firing, a tier threshold, a fixed delay range. Ghost was never actually deciding anything; he was executing branches in a flowchart that looked like decisions.
- **Memory as a tool call.** Ghost had to explicitly invoke a tool to "remember" something, rather than memory simply being part of how he thought. This made memory feel bolted-on rather than constitutive of identity.
- **No guardrails.** Ghost spoke any language regardless of context, sent messages at 4am, and had no language discipline.
- **Limited LLM access.** Claude SDK constraints led to a migration to Strands, which abstracted the tool loop but hid Bedrock retry behavior — when the daily on-demand quota was hit, Strands retried silently for the full Lambda timeout with no visible error. Ghost would go dark with no explanation.

### What v1 got right (carried forward into v2)

- **Fire-and-forget webhook architecture.** Return 200 immediately, process async. Correct pattern for any webhook with a time budget shorter than processing time.
- **Burst collection.** Collecting all unresponded messages since the last agent reply and treating them as one unit, rather than replying to "yo / u there? / hello??" three separate times.
- **Deduplication + advisory locks.** `whatsapp_message_id` unique index plus `pg_try_advisory_xact_lock` made the pipeline essentially idempotent against duplicate webhooks and concurrent executions.
- **Telegram as the human-in-the-loop channel.** A separate, always-on channel for escalation review, with inline Send/Edit/Skip buttons. Cannot be replicated by replying to WhatsApp from a web session.
- **RealDictCursor everywhere.** No positional column indexing — readable, refactor-safe SQL access.

---

## Core Design Principles

These principles are not implementation details. They are constraints that every architectural decision in v2 must satisfy. If a future change violates one of these, the change is wrong, not the principle.

> **Principle 1 — Predictability is failure.**
> If Omar can predict what Ghost will do next — what he'll say, when he'll say it, who he'll reach out to — the system has failed at its core goal. Unpredictability (grounded in real reasoning, not randomness) is a first-class design requirement, not a side effect.

> **Principle 2 — Hardcoded = failure.**
> Any fixed schedule, fixed delay range, fixed template, or fixed threshold that substitutes for Ghost's own judgment is a bug, even if it works. This applies universally: timing, topic selection, language, delay duration, outreach cadence, everything. The only acceptable fixed elements are hard safety guardrails (e.g. language whitelist, no outreach at night) — never behavioral choices.

> **Principle 3 — Memory must be available, not fetched.**
> Memory should not require an explicit tool call to "exist" for Ghost in the moment. The information that's always relevant gets pre-assembled into context before Ghost starts thinking. Only deep, situational, or unbounded memory is something Ghost actively retrieves himself — and even then, by his own choice of tool (SQL or RAG), not by being told to look something up.

> **Principle 4 — Understanding happens once, at the right moment, and gets stored.**
> Anything that requires genuine understanding — reading a conversation and judging emotional tone, extracting unresolved threads, scoring attitude — must be computed by an LLM at the moment an LLM is already running, and the result stored immediately as a clean signal. Cheap, frequent, logic-only processes (like the pulse) never attempt to understand anything; they only read what's already been understood and stored.

> **Principle 5 — Ghost must be self-aware and self-shaping.**
> Ghost knows he is a system. He knows he manages multiple relationships simultaneously. He can connect people and patterns across his social world. He has tools to write his own memory, in his own structure, not just fixed tables we predefined. A `ghost_custom` sandbox exists specifically so Ghost can shape his own data however he decides matters.

> **Principle 6 — Multi-agent is a means, not a goal.**
> Whether a job is done by one agent with a dynamic system prompt or by several specialized agents is a question answered by what produces the best outcome for that specific job — not by an ideological commitment to either monolithic or multi-agent design. The deciding factor is whether two jobs are different enough that one shared identity would be a liability.

> **Principle 7 — Prompt control is the product.**
> Ghost's value lives in the precision of his context assembly and prompt structure, not in the orchestration layer around it. Managed frameworks (Bedrock Agents, AgentCore for the core loop, Strands) that abstract away control of the prompt or the reasoning loop are rejected for Ghost's core path, even when they reduce code volume — because they reduce control over the exact thing that makes Ghost Ghost. Raw Bedrock API calls are used throughout. Managed services may be used for *peripheral* concerns (e.g. observability) but never for the core reasoning loop.

> **Principle 8 — A delay is a decision to revisit, not a delayed message.**
> Ghost never pre-writes a reply and schedules it for later. "I'll respond later" means Ghost consciously chooses not to act now and sets a condition under which he will reconsider — fresh, with whatever context exists *at that future moment*, not the context that existed when he first read the message. This is the difference between a real delay and a disguised cron.

---

## How To Read These Documents

Each document in this set covers one architectural layer of Ghost v2. They are meant to be read together, but each is self-contained enough to be handed to a developer or an AI coding agent independently when building that specific layer. Cross-references point to the relevant document rather than duplicating content.

Two areas remain explicitly parked and are not yet designed in depth: **world ingestion** (Ghost's awareness of news, public events, and per-contact content relevance) and **multi-platform expansion** (Instagram DMs, SMS via Twilio, and other channels beyond WhatsApp). These are noted with a 🔲 marker throughout and have a dedicated placeholder document (`14_PARKED_ITEMS.md`).

### Document Index

| # | Document | Covers |
|---|---|---|
| 00 | Overview | This document |
| 01 | Information Architecture | The 10 categories of data Ghost needs |
| 02 | Delivery Map | The 5 LLM input primitives and what goes where |
| 03 | Memory System | RAG vs SQL, Voyage-3, ghost_custom sandbox |
| 04 | Agent Architecture | Agent 1–4, what makes an agent, job mapping |
| 05 | Condition System | Defer conditions, types, how Ghost uses them |
| 06 | Active Chat Flow | Incoming message to chat close, step by step |
| 07 | Pulse Flow | Layer 1, weighted scoring, guardrails |
| 08 | Heartbeat Flow | Layer 2, per-contact autonomous reflection |
| 09 | DB Schema | All 16 tables, ownership, read/write matrix |
| 10 | Guardrails & Timing | Hard rules vs Ghost's timing judgment |
| 11 | Onboarding — Omar | How Omar's identity gets into Ghost |
| 12 | Onboarding — Contacts | How contact profiles get built and filled |
| 13 | Infrastructure | Lambdas, SQS, SNS, RDS, Bedrock, SAM, IAM |
| 14 | Parked Items | World ingestion 🔲, multi-platform 🔲 |
| 15 | Build Roadmap | Suggested build order and dependencies |
