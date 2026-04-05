# Ghost — AI Social Twin

Fully autonomous WhatsApp agent that replies as you — with memory, personality, persistent mood, and social intelligence. You stay in the loop via a Telegram side-channel and a local debug dashboard.

---

## What it does

Ghost lives inside your WhatsApp and handles conversations on your behalf. It knows who you're talking to, remembers everything about them, mirrors your voice, and decides when to reply, what to say, and when to stay silent. When it's unsure — crisis, real-world request, authenticity challenge — it escalates to you on Telegram with a draft reply you can send, edit, or skip.

---

## Architecture

```
WhatsApp webhook
      ↓
webhook_receiver        — parse inbound message → invoke orchestrator async
      ↓
orchestrator            — Claude agent loop (tool use)
      │
      │  tools: search_memories, get_history, save_memory,
      │         get_contact_profile, update_contact_profile,
      │         get_mood_state, update_mood,
      │         delay_reply, request_human_review, update_conversation_arc
      │
      ├──→ whatsapp_sender      (auto-send)
      ├──→ telegram_bot         (escalation → Send / Edit / Skip)
      └──→ SQS delay queue      (delayed re-invocation)

proactive_engine        — scheduled every 2h, sends follow-ups autonomously
```

**Infrastructure:** API Gateway → Lambda → RDS PostgreSQL 15 + pgvector + SQS + SNS  
**Secrets:** all via SSM Parameter Store — nothing hardcoded  
**IaC:** AWS SAM (`template.yaml`)

---

## Stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| Compute | AWS Lambda |
| LLM | Claude `claude-sonnet-4-20250514` (Anthropic SDK, native tool use) |
| Database | RDS PostgreSQL 15 + pgvector |
| Async queue | SQS (up to 15 min delay) |
| Event routing | SNS |
| Secrets | SSM Parameter Store |
| WhatsApp | Meta Cloud API |
| Side-channel | Telegram Bot API |
| IaC | AWS SAM |
| Dashboard | Next.js 15, Tailwind, direct RDS connection |

---

## Project structure

```
template.yaml                     SAM IaC — all Lambda, SQS, SNS, API GW
samconfig.toml                    SAM CLI config (dev / prod)
Makefile                          all commands (see below)

layers/ghost_common/python/
  ssm.py                          SSM loader with in-process cache
  db.py                           psycopg2 connection pool + get_cursor()
  models.py                       all Pydantic v2 models
  whatsapp.py                     Meta Cloud API client

functions/
  webhook_receiver/               GET verify + POST parse → orchestrator
  orchestrator/
    handler.py                    entry point + _process pipeline
    agent.py                      Claude agent loop + system prompt
    tools.py                      tool handlers + Anthropic schema
    db_helpers.py                 all DB ops (contact, conversation, message, trace)
    dispatch.py                   SQS / Lambda / SNS invocations
    debug.py                      Telegram dev trace block
  whatsapp_sender/                sends via Meta Cloud API + typing indicator
  telegram_bot/                   SNS escalation + Send/Edit/Skip callbacks
  proactive_engine/               scheduled follow-ups + check-ins

migrations/
  versions/001_initial_schema.py  full schema + pgvector + IVFFlat index
  versions/002_add_persona_to_knowledge_chunks.py
  versions/003_add_whatsapp_message_id.py
  versions/004_ghost_state.py     persistent mood state table
  versions/005_agent_traces.py    per-reply agent loop trace table

scripts/
  admin.py                        CLI: contact, remember, me, show, contacts, mood, send, proactive
  ingest_whatsapp.py              WhatsApp export ingestion

dashboard/                        local Next.js debug platform
  app/
    page.tsx                      home — stats + ghost state + recent convos
    conversations/[id]/page.tsx   messages + expandable agent traces ← primary debug view
    contacts/[phone]/page.tsx     contact editor + memory manager
    mood/page.tsx                 ghost state editor
  components/
    TraceBlock.tsx                collapsible tool call trace
    MoodPanel.tsx                 ghost state display
  lib/db.ts                       direct RDS connection
```

---

## SSM parameters

```
/ghost/{env}/whatsapp/token
/ghost/{env}/whatsapp/phone_number_id
/ghost/{env}/whatsapp/verify_token
/ghost/{env}/anthropic/api_key
/ghost/{env}/telegram/bot_token
/ghost/{env}/telegram/chat_id
/ghost/{env}/db/connection_string
```

---

## Makefile commands

```bash
make deploy-dev          # SAM build + deploy to dev
make deploy-prod         # SAM build + deploy to prod (with confirmation)
make update              # fast handler-only push (zip + lambda update-function-code)
make migrate             # run Alembic migrations (requires DATABASE_URL env var)
make layer-install       # install layer deps (manylinux wheels for Lambda)

make dashboard-install   # npm install inside dashboard/
make dashboard           # fetch DATABASE_URL from SSM + start Next.js dev server

make contact   PHONE=33744746977 NAME="Alice" TIER=1
make remember  PHONE=33744746977 TEXT="Has a dog called Max"
make me        TEXT="I hate small talk"
make show      PHONE=33744746977
make contacts
make send      PHONE=33744746977 TEXT="yo"
make mood
make mood      NOTES="bad week" AVAILABILITY=light ENERGY=0.4
make proactive PHONES=33652469989,33664970571

make db                  # live psql session against dev DB
make telegram-webhook    # register Telegram webhook URL (run once after deploy)
```

---

## Setup

**1. Layer dependencies** (Linux-compatible wheels for Lambda)
```bash
make layer-install
```

**2. DB migrations**
```bash
export DATABASE_URL=$(aws ssm get-parameter \
  --name /ghost/dev/db/connection_string \
  --with-decryption --query Parameter.Value --output text --region eu-west-1)
make migrate
```

**3. Deploy**
```bash
make deploy-dev
```

**4. Dashboard**
```bash
make dashboard-install
make dashboard   # auto-fetches DATABASE_URL from SSM
```

---

## WhatsApp token rotation

Tokens expire every ~24h. Update:

```bash
aws ssm put-parameter \
  --name "/ghost/dev/whatsapp/token" \
  --value "NEW_TOKEN" \
  --type SecureString --overwrite --region eu-west-1
```

Force Lambda cold starts to flush SSM cache:

```bash
for fn in ghost-webhook-receiver-dev ghost-orchestrator-dev ghost-whatsapp-sender-dev; do
  aws lambda update-function-configuration \
    --function-name $fn --region eu-west-1 \
    --environment "Variables={RELOAD=$(date +%s)}"
done
```

---

## How Ghost thinks

Each inbound message triggers a Claude agent loop. Claude has 10 tools:

| Tool | What it does |
|---|---|
| `search_memories` | full-text search over knowledge_chunks |
| `get_history` | fetch recent conversation messages |
| `get_contact_profile` | name, tier, voice profile, notes |
| `save_memory` | write a new knowledge chunk |
| `update_contact_profile` | update name / tier / notes |
| `get_mood_state` | read persistent ghost_state |
| `update_mood` | update energy / battery / load / availability |
| `delay_reply` | exit loop and re-invoke via SQS after N seconds |
| `request_human_review` | exit loop and escalate to Telegram |
| `update_conversation_arc` | mark conversation open / flowing / winding_down / dormant |

Claude decides what it needs. It fetches history only when relevant, saves memories when it learns something, updates mood after heavy exchanges, and delays or escalates when warranted.

---

## Roadmap

### Done ✓
- Full agent loop (Claude with 10 tools)
- Persistent ghost_state (mood/energy/battery managed by Claude + admin CLI)
- Burst detection, deduplication, advisory lock
- SQS delay queue
- Telegram escalation with Send / Edit / Skip
- Proactive engine (scheduled follow-ups + check-ins)
- WhatsApp export ingestion + voice profile extraction
- Local Next.js debug dashboard with live agent traces
- Admin CLI (`make contact / remember / me / mood / send / proactive`)

### Remaining
- pgvector semantic search (replace tsvector full-text)
- Confidence-based auto-escalation (currently always 1.0)
- Override learning loop (Telegram edits → behavioral knowledge_chunks)
- Conversation arc tracker (state machine per conversation)
- Long-delay support (DynamoDB TTL for delays >15 min)
- Calendar integration (meeting-heavy days → low engagement mode)
