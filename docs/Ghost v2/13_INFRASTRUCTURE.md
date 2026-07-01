# 13 — Infrastructure

## Purpose

This document maps every architectural concept from the previous documents onto actual AWS components: what runs where, what triggers what, and how it's deployed. Region: `eu-west-1`, consistent with v1. Naming convention carried forward: `ghost-{resource}-{env}`.

---

## Lambda Functions

One Lambda per job, matching the agent and flow boundaries established in `04_AGENT_ARCHITECTURE.md`, `06_ACTIVE_CHAT_FLOW.md`, `07_PULSE_FLOW.md`, and `08_HEARTBEAT_FLOW.md`.

| Function | Role |
|---|---|
| `ghost-webhook-receiver` | API Gateway POST target. GET handles Meta's verify-token handshake. POST parses the payload, returns 200 immediately, pushes to `inbound-message-queue`. |
| `ghost-agent-perception` | Agent 1. Consumes `inbound-message-queue` (after burst collection), produces structured classification, pushes to `perception-output-queue`. |
| `ghost-agent-ghost` | Agent 2 — the core Ghost identity. Consumes `perception-output-queue` (active chat mode) or `heartbeat-queue` (heartbeat mode). Dynamic system prompt per `04_AGENT_ARCHITECTURE.md`. |
| `ghost-agent-memory` | Agent 3. Consumes `memory-processing-queue`. Reads closed conversations, writes signals back to the DB. |
| `ghost-pulse` | Layer 1. Self-perpetuating via `pulse-queue`. Pure logic, no LLM call. Full detail in `07_PULSE_FLOW.md`. |
| `ghost-whatsapp-sender` | Consumes `outbound-message-queue` (FIFO). Typing indicator → reasoned delay → send via WhatsApp Business API. |
| `ghost-telegram-bot` | Two roles: SNS-triggered escalation card rendering (via `escalation-queue`), and API Gateway POST `/telegram` handling button callbacks and edited replies. |
| `ghost-context-assembler` | Shared library/function invoked by both `ghost-agent-ghost` paths to build the Tier 1 pre-assembled context package per `02_DELIVERY_MAP.md`, specialized per call type as defined in the relevant flow document. |
| `ghost-long-delay-trigger` | Fired by the DynamoDB Stream when a long-delay TTL record expires. Pushes the deferred item back onto `inbound-message-queue` so it re-enters the normal pipeline with fresh context. |
| `ghost-world-ingestion` 🔲 | Parked — see `14_PARKED_ITEMS.md`. |

---

## Triggers

```
API Gateway POST /webhook        → ghost-webhook-receiver
API Gateway POST /telegram       → ghost-telegram-bot
SQS inbound-message-queue        → ghost-agent-perception (after burst window)
SQS perception-output-queue      → ghost-agent-ghost (active chat mode)
SQS heartbeat-queue               → ghost-agent-ghost (heartbeat mode)
SQS memory-processing-queue       → ghost-agent-memory
SQS pulse-queue                    → ghost-pulse (self re-enqueues every 60-120s)
SQS outbound-message-queue (FIFO)  → ghost-whatsapp-sender
SNS ghost-escalations               → escalation-queue → ghost-telegram-bot
DynamoDB Stream (TTL expiry)          → ghost-long-delay-trigger
EventBridge (world ingestion only) 🔲 → ghost-world-ingestion
```

---

## SQS Queues

This is the area most heavily revised from an initial draft during design — every handoff in the system was deliberately moved onto SQS rather than direct async Lambda invocation, specifically because this is fundamentally a messaging system, and SQS gives retry, dead-letter handling, and message persistence at every step instead of risking silent message loss at any single hop.

| Queue | Purpose | Notes |
|---|---|---|
| `pulse-queue` | Drives the self-perpetuating pulse loop | Standard queue, `DelaySeconds` 60-120s on re-enqueue |
| `inbound-message-queue` | Every incoming message, feeds perception | Standard queue, retry + DLQ — no inbound message is ever silently dropped |
| `perception-output-queue` | Perception's structured output, feeds Ghost | Standard queue; also absorbs bursts so simultaneous messages from multiple contacts queue rather than overwhelm Ghost's Lambda concurrently |
| `outbound-message-queue` | Ghost's replies, feeds the WhatsApp sender | **FIFO**, partitioned by contact phone number as the message group ID — guarantees in-order delivery per contact (critical for multi-part replies) while still allowing full parallelism across different contacts |
| `heartbeat-queue` | One message per flagged contact, feeds heartbeat | Standard queue with a configured concurrency limit — controls how many heartbeats fire simultaneously when pulse flags several contacts in one cycle |
| `memory-processing-queue` | Closed conversations, feeds Agent 3 | Standard queue, fully decoupled and non-urgent — no impact on response latency |
| `escalation-queue` | SNS subscriber, feeds the Telegram bot | Standard queue, gives retry on Telegram API failures that a raw SNS-to-Lambda subscription wouldn't |
| `world-ingestion-queue` 🔲 | Parked | See `14_PARKED_ITEMS.md` |

`pulse-queue` starts empty on a fresh deploy, and nothing would ever send it a first message since the loop only perpetuates itself once running. `template.yaml` seeds it automatically with a `Custom::PulseLoopSeed` resource (backed by `ghost-pulse-seeder`) that fires exactly once, on stack **creation** only - `Update`/`Delete` are no-ops so redeploys never enqueue a second message and spin up a concurrent loop.

**8 queues total.** Every handoff identified across `06`, `07`, and `08` is backed by exactly one of these.

---

## Long Delays Beyond SQS's 15-Minute Limit

SQS's native `DelaySeconds` caps at 900 seconds (15 minutes), which is sufficient for short reasoned reply delays but not for conditions like "reply in 6 hours" or "check on this tomorrow." For anything longer:

**DynamoDB TTL pattern:**
1. When Ghost (or pulse) needs a delay longer than 15 minutes, a record is written to the `ghost-long-delays` DynamoDB table with `TTL = now + delay_seconds`.
2. A DynamoDB Stream is configured on this table.
3. When the TTL expires and DynamoDB removes the item, the Stream fires `ghost-long-delay-trigger`.
4. That Lambda pushes the relevant item back onto `inbound-message-queue` (if it's a deferred reply) or directly into the pulse's evaluation path (if it's a condition check), ensuring the eventual action is always made with fresh context, never a stale pre-written one — consistent with `05_CONDITION_SYSTEM.md`.

```
ghost-long-delays (DynamoDB)
  pk: delay_id
  contact_phone
  defer_condition_id
  TTL: expiry_timestamp
```

In practice, most of the system's actual timing logic runs through the pulse's continuous condition evaluation (`07_PULSE_FLOW.md`) rather than this DynamoDB pattern — this pattern exists specifically as the mechanism for delays whose duration exceeds what a 1-2 minute pulse cycle would reasonably want to poll for directly, or as an optimization to avoid keeping very-long-lived rows in `defer_conditions` under active polling.

---

## SNS Topics

```
ghost-escalations    — triggers the escalation-queue → ghost-telegram-bot path
ghost-alerts          — system-level alerts: Bedrock quota exhaustion, Lambda
                         timeouts, RDS connection failures, pulse loop death
```

---

## RDS

PostgreSQL 15 with the `pgvector` extension, single instance, `eu-west-1`. All 16 active tables from `09_DB_SCHEMA.md` live here. Accessed exclusively through **RDS Proxy**, which provides connection pooling across the many concurrently-invoked Lambdas in this architecture — without it, the number of simultaneous Lambda executions (especially during a burst of heartbeats) could exhaust RDS's native connection limit.

---

## Bedrock

Raw Bedrock API calls throughout — never Bedrock Agents, never AgentCore for the core reasoning loop (full reasoning for this decision in `04_AGENT_ARCHITECTURE.md` and restated as Principle 7 in `00_OVERVIEW.md`).

**Model selection per agent:**

| Agent | Model | Why |
|---|---|---|
| Agent 1 — Perception | Claude Haiku | Cheap, fast classification; doesn't need Ghost's identity or Sonnet-level reasoning |
| Agent 2 — Ghost | Claude Sonnet | This is the agent whose output is actually seen by Omar's contacts — quality matters most here |
| Agent 3 — Memory Processor | Claude Haiku | Extraction and summarization; doesn't need Sonnet-level quality |
| Heartbeat (Agent 2 in heartbeat mode) | Claude Sonnet | Ghost reflecting and deciding — quality matters as much here as in active chat |

**Embeddings:** Voyage-3 multilingual, via Bedrock, for everything written to `memories.embedding` (see `03_MEMORY_SYSTEM.md` for why this specific model was chosen over v1's Titan/Voyage dual-path approach).

**Fallback:** if Bedrock quota is exhausted, fall back to the Anthropic API directly via an API key stored in SSM. This directly addresses a documented v1 failure mode: Strands' internal retry behavior on Bedrock throttling was opaque, retrying silently for the full Lambda timeout with no visible error — v2's raw-API approach (Principle 7) makes this kind of failure visible and explicit rather than hidden inside a managed framework's retry loop.

### Why not Bedrock Agents

Bedrock Agents manages the reasoning loop, tool execution, and session state, but also manages the system prompt *partially* — and Ghost's entire value proposition is the precision of his context assembly and prompt structure. Handing partial prompt control to AWS is a direct liability for a system this dependent on exact control over every token. Also more expensive per token, with an opaque reasoning loop that's harder to debug than a framework's, and built-in session memory that doesn't match the custom multi-layered memory system in `03_MEMORY_SYSTEM.md` and `09_DB_SCHEMA.md`.

### Why not AgentCore for the core loop

AgentCore (AWS's newer, more flexible managed agent runtime) offers managed long-term memory, better tool observability, built-in session management, and more prompt flexibility than Bedrock Agents. It was seriously considered. The conclusion: AgentCore's managed memory could simplify parts of the DB schema, and its observability is genuinely valuable — but adopting it for the *core reasoning loop* still risks the same fundamental issue as Bedrock Agents, at a smaller scale: ceding any control over the precise mechanics of Ghost's reasoning to a managed service, when the lesson directly learned from v1's experience with Strands was "own the loop." 

**Where AgentCore is used:** purely as an optional *observability and tracing* layer on top of the raw Bedrock calls — never as a replacement for them.

---

## SSM Parameter Store

All secrets and environment-scoped configuration. The path structure explicitly fixes a documented v1 bug, where `whatsapp.py` used an un-scoped path (`/ghost/whatsapp/token`, no `{env}`) causing dev and prod to share the same WhatsApp token:

```
/ghost/{env}/whatsapp/token
/ghost/{env}/whatsapp/phone_id
/ghost/{env}/telegram/bot_token
/ghost/{env}/db/connection_string
/ghost/{env}/bedrock/region
/ghost/{env}/anthropic/api_key
/ghost/{env}/voyage/api_key
```

Every parameter in v2 is environment-scoped without exception.

---

## EventBridge

Used in exactly **one** place in this architecture: the parked world ingestion flow (`14_PARKED_ITEMS.md`), which is the one component that genuinely needs a calendar-style schedule rather than a reactive or self-perpetuating loop. Pulse explicitly does **not** use EventBridge — see `07_PULSE_FLOW.md` for why the SQS self-perpetuating pattern was chosen instead.

---

## DynamoDB

One table, used exclusively for the long-delay TTL pattern described above:

```
ghost-long-delays
  pk: delay_id
  contact_phone
  defer_condition_id
  TTL: expiry_timestamp
```

---

## SAM

Infrastructure as code via a single `template.yaml` defining every Lambda function, every SQS queue, the SNS topics, API Gateway, the one EventBridge rule, the DynamoDB table, and all IAM roles. Deployed with `sam deploy`. For fast iteration on Lambda handler code specifically (not infrastructure changes), the `make update` pattern from v1 is carried forward — zip and `aws lambda update-function-code` for all functions in roughly 15 seconds, far faster than a full SAM deploy when only application logic changed.

---

## IAM

Least privilege, scoped per Lambda function to exactly what it touches:

- `ghost-agent-ghost` — Bedrock invoke, RDS read/write (via RDS Proxy), relevant SQS send/receive
- `ghost-pulse` — RDS read/write only, plus SQS send to `heartbeat-queue` and `memory-processing-queue`. No Bedrock permission at all — this is enforced at the IAM level, not just by convention, since pulse must never be able to make an LLM call under any circumstance
- `ghost-agent-perception` and `ghost-agent-memory` — Bedrock invoke (Haiku only, where model access can be scoped), RDS read/write, relevant SQS
- `ghost-whatsapp-sender` — WhatsApp Business API credentials (via SSM), SQS receive only
- `ghost-telegram-bot` — Telegram API credentials (via SSM), SNS subscribe, RDS read/write

No function holds blanket or administrative access.

---

## Environments

Dev and prod are fully separated: distinct SSM parameter paths (per the `{env}` scoping above), distinct RDS instances, and ideally distinct WhatsApp Business numbers. No shared state of any kind between environments.

---

## Monitoring

CloudWatch logs per Lambda function. Alerts routed through `ghost-alerts` (SNS) for:
- Bedrock quota exhaustion
- Lambda timeouts
- RDS connection failures
- Pulse loop death — specifically, the self-perpetuating SQS loop failing to re-enqueue itself, which would otherwise silently stop Ghost's entire autonomous layer with no obvious symptom until someone noticed Ghost had gone quiet
