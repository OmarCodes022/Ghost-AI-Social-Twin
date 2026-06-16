# 14 — Parked Items

## Purpose

This document holds everything explicitly identified during design as relevant and necessary, but deliberately not yet architected in depth — placeholders preserved so nothing gets forgotten or silently dropped, exactly as requested when each was parked. Both items below are referenced with a 🔲 marker throughout the rest of this document set wherever they would otherwise plug in.

---

## 🔲 World Ingestion

### What it's for

When asked what "the world" should mean to Ghost, the answer given was direct: all of it — and that Ghost should be able to detect a contact's interests and adapt accordingly. This produces category 3 ("The World Right Now") from `01_INFORMATION_ARCHITECTURE.md`, and feeds the "world relevance" scoring signal referenced throughout `07_PULSE_FLOW.md`.

### Identified sources

- **Omar's own world** — his calendar, his life events and context (some manually entered, some extractable from conversations he has, by Ghost or by Agent 3)
- **The public world** — tech and AI news, general news, trending topics
- **Per-contact world** — each contact's detected interests (extracted from conversation history, the same way Agent 3 extracts any other fact), content relevant to those interests, and potentially their own social signals (stories, posts, activity) if ever made accessible

### The output shape, already agreed in principle

Regardless of source, ingestion is expected to normalize into one consistent structure so that pulse can read it without needing to understand anything about where it came from:

```json
{
  "event": "OpenAI announced GPT-5",
  "tags": ["AI", "tech", "OpenAI"],
  "relevance": ["contacts who follow AI", "contacts interested in coding"],
  "timestamp": "...",
  "urgency": "low"
}
```

Pulse would then do a simple tag match against each contact's known interests (`contacts` / `memories`) — no LLM involved in that matching step, consistent with Principle 4 from `00_OVERVIEW.md`. The understanding (tagging, categorizing, determining relevance) happens once, at ingestion time, by an LLM (Agent 4, per `04_AGENT_ARCHITECTURE.md`) — not repeatedly at read time.

### What remains genuinely undesigned

- What triggers ingestion, and how often (a true calendar schedule via EventBridge was tentatively proposed in `13_INFRASTRUCTURE.md` as the one legitimate use of EventBridge in this architecture, but the actual cadence and source-polling strategy is not decided)
- The specific source integrations (which news APIs, how calendar sync actually works, whether/how social signals would ever be accessed)
- The full schema for the `world_events` table (table 13 in `09_DB_SCHEMA.md` is reserved but undefined)
- How per-contact interest detection actually gets triggered — presumably as part of Agent 3's post-chat-close extraction, but this has not been confirmed
- The `ghost-world-ingestion` Lambda's actual implementation (reserved in `13_INFRASTRUCTURE.md`, not built)
- The `world-ingestion-queue` SQS queue's actual message contract (reserved, not defined)

---

## 🔲 Multi-Platform Expansion

### What's been identified

WhatsApp is the confirmed, sole platform for the entire architecture described in this document set. Beyond WhatsApp, candidate platforms were named without being designed:

- **Strong candidates:** Instagram DMs, SMS (via Twilio)
- **Deprioritized:** Snapchat, LinkedIn, Twitter/X

### What remains genuinely undesigned

- Whether platform expansion means literally running parallel pipelines (separate webhook receivers, separate sender Lambdas) that all funnel into the same Agent 2 / Ghost core, or something more unified
- How a single contact who reaches Ghost across multiple platforms should be represented in the schema — `contacts.phone_number` is currently the primary key, which assumes a phone-number-centric identity model that would need rethinking for a platform like Instagram where the identifier isn't a phone number
- Whether per-platform voice or behavior differences are needed (e.g., does Ghost behave differently on SMS vs. WhatsApp), and if so, whether that's modeled as an extension of `per_person_rules` or something new entirely
- Twilio-specific infrastructure (a new webhook receiver, a new sender Lambda, SMS-specific guardrails around message length and cost)

---

## How These Connect Back

Every other document in this set references these two items only as placeholders — nothing downstream assumes they exist yet. `07_PULSE_FLOW.md`'s world-relevance scoring signal is designed to function correctly with this input simply absent (it contributes zero weight until it exists). `09_DB_SCHEMA.md` reserves table 13 without defining it. `13_INFRASTRUCTURE.md` reserves the Lambda, queue, and EventBridge rule without implementing them. When either of these is ready to be designed in full, it should follow the same process used for every other flow in this set: define the trigger, define what gets read and written, define the agent (if any) involved, and lock it into the relevant documents before implementation begins.
