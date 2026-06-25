# Ghost

> I gave an AI real autonomy and let it run my social life. It decides who deserves a reply today, who gets left on read, and who it reaches out to first. Without me touching my phone.



Ghost is an autonomous WhatsApp agent that texts as me. Not a bot that replies when asked - an agent that decides for itself who to contact, when, what to say, and when to stay silent. I don't touch my phone. Ghost handles it.

The hard part isn't the replies. It's the autonomy. Most "autonomous" agents have a cron job where the brain should be. Ghost doesn't.



## What real autonomy looks like here

**No schedules.** A pulse loop runs every 60–120 seconds, reads real signals - attitude trends, mood, open threads, life events, time of day per contact's timezone - accumulates a weighted score, and only wakes Ghost up when something genuinely warrants attention. Ghost then decides what to do. Including nothing, which is a valid outcome.

**No pre-written replies.** When Ghost decides not to reply now, he writes a *condition* - what would make him reconsider - and sleeps. When it resolves (mood shifted, contact replied, their exam passed), he wakes with fresh context and makes a new decision. He is never executing something he pre-wrote.

**No fixed delay ranges.** Reply timing is a byproduct of Ghost reasoning about the relationship - how fast he's been replying lately, the contact's urgency, his current social battery, his goal for that relationship. The duration falls out of the reasoning.

**No identity fragmentation.** Ghost is one entity across three modes (responding, reflecting, initiating) with a single dynamic system prompt where the job rotates but the identity never does. He tracks his own mood, intentions, and relationship decisions across every contact simultaneously.



## How it works

Two layers, strictly separated:

**Pulse** - pure logic, no LLM, runs every 60–120s. Reads pre-computed signals, evaluates conditions mechanically, scores every contact, applies hard guardrails, flags what needs attention. Never tries to understand anything.

**Heartbeat** - Ghost, one invocation per flagged contact. Scratchpad reasoning, optional SQL or RAG retrieval (his choice), then a decision: reach out, reply to a deferred message, stay silent, update his state, revise an intention, or do nothing.

Active chat flow:

```
Message → SQS
    ↓
Agent 1 (Haiku) - language, emotion, intent, urgency, attitude shift
    ↓
Context assembled - identity, mood, contact profile, history, few-shots
    ↓
Ghost (Sonnet) - scratchpad reasoning, optional SQL/RAG
    ↓
    ├── Reply now        → queue → typing indicator → reasoned delay → send
    ├── Consciously wait → writes condition + reasoning, sleeps
    └── Escalate         → Telegram: Send / Edit / Skip
    ↓
Ghost updates mood, stance, intentions inline
    ↓
Pulse (every 60-120s, no LLM)
    ├── Close condition met → conversation closes
    │       ↓
    │   Agent 3 (Haiku) - extracts attitude scores, facts,
    │   unresolved threads, gaps → feeds future pulse cycles
    │
    └── Contact score threshold crossed
            ↓
        Heartbeat - Ghost decides: reach out, reply to something he
        waited on, stay silent, update state, or do nothing.
        All autonomous action originates here.
```

Memory: Ghost has two tools - SQL for precise structured lookups, RAG via Voyage-3 multilingual embeddings for semantic retrieval across French, English, and Arabic. He decides which to use. Nothing is auto-injected. He also has a `ghost_custom` table he designed himself. His own schema, we don't touch it.



## Stack

| Layer | What |
|---|---|
| Compute | AWS Lambda, one function per job |
| Queues | 8 SQS queues - every handoff backed by one |
| Database | RDS PostgreSQL 15 + pgvector, RDS Proxy |
| LLM | Raw Bedrock API - no LangChain, no Bedrock Agents, no frameworks |
| Embeddings | Voyage-3 multilingual, `vector(1024)`, one model, no fallback |
| IaC | AWS SAM |
| Escalation | Telegram bot, inline Send / Edit / Skip |



## Principles

**Predictability is failure.** If you can predict what Ghost will do next, the system has failed.

**Hardcoded = failure.** Any fixed schedule, delay, or template substituting for Ghost's judgment is a bug - even if it works.

**A delay is a decision to revisit, not a delayed message.** Ghost never pre-writes and schedules. He sets a condition and decides fresh when it resolves.

**Prompt control is the product.** No framework touches the core reasoning loop.



## Docs

Full architecture documented across 17 files in [`/docs`](docs/Ghost%20v2/) - information design, agent architecture, memory system, every flow in detail, database schema, infrastructure, build roadmap. Every decision includes the reasoning trail and explicitly rejected alternatives.

| # | Doc |
|---|-----|
| 00 | [Overview](docs/Ghost%20v2/00_OVERVIEW.md) |
| 01 | [Information Architecture](docs/Ghost%20v2/01_INFORMATION_ARCHITECTURE.md) |
| 02 | [Delivery Map](docs/Ghost%20v2/02_DELIVERY_MAP.md) |
| 03 | [Memory System](docs/Ghost%20v2/03_MEMORY_SYSTEM.md) |
| 04 | [Agent Architecture](docs/Ghost%20v2/04_AGENT_ARCHITECTURE.md) |
| 05 | [Condition System](docs/Ghost%20v2/05_CONDITION_SYSTEM.md) |
| 06 | [Active Chat Flow](docs/Ghost%20v2/06_ACTIVE_CHAT_FLOW.md) |
| 07 | [Pulse Flow](docs/Ghost%20v2/07_PULSE_FLOW.md) |
| 08 | [Heartbeat Flow](docs/Ghost%20v2/08_HEARTBEAT_FLOW.md) |
| 09 | [DB Schema](docs/Ghost%20v2/09_DB_SCHEMA.md) |
| 10 | [Guardrails and Timing](docs/Ghost%20v2/10_GUARDRAILS_AND_TIMING.md) |
| 11 | [Onboarding - Omar](docs/Ghost%20v2/11_ONBOARDING_OMAR.md) |
| 12 | [Onboarding - Contacts](docs/Ghost%20v2/12_ONBOARDING_CONTACTS.md) |
| 13 | [Infrastructure](docs/Ghost%20v2/13_INFRASTRUCTURE.md) |
| 14 | [Parked Items](docs/Ghost%20v2/14_PARKED_ITEMS.md) |
| 15 | [Build Roadmap](docs/Ghost%20v2/15_BUILD_ROADMAP.md) |
| 16 | [Ingestion Pipeline](docs/Ghost%20v2/16_INGESTION_PIPELINE.md) |