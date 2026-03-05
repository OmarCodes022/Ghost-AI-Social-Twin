# Ghost — AI Social Twin

Fully autonomous WhatsApp agent that responds as you — with memory, personality, mood, and social intelligence.

---

## What it does

Ghost lives inside your WhatsApp and replies on your behalf. It knows who you're talking to, remembers everything about them, mirrors your voice, and decides when to reply, what to say, and when to stay silent. The goal is presence — every contact should feel like they're genuinely talking to you.

---

## Architecture

Pure serverless on AWS. Nine Lambda functions, zero idle servers.

```
WhatsApp webhook
      ↓
webhook_receiver          — parses inbound message, invokes orchestrator async
      ↓
orchestrator              — main flow controller
      ↓
  ┌───────────────────────────────────────┐
  │  mood_engine          mood vector     │
  │  timing_engine        reply now?      │  intelligence layer
  │  escalation_detector  sensitive?      │
  │  memory_retriever     relevant chunks │
  │  response_generator   draft reply     │
  └───────────────────────────────────────┘
      ↓                        ↓
whatsapp_sender          telegram_bot
(auto-send)              (escalation → you review)
```

**Infrastructure:** API Gateway → Lambda → RDS PostgreSQL + pgvector + SQS + SNS
**Secrets:** all via SSM Parameter Store, nothing hardcoded
**IaC:** AWS SAM (`template.yaml`)

---

## Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.12 |
| Compute | AWS Lambda |
| Database | RDS PostgreSQL 15 + pgvector |
| Async queue | SQS (up to 15 min native delay) |
| Event routing | SNS |
| Secrets | SSM Parameter Store |
| LLM | Claude (`claude-sonnet-4-20250514`) |
| WhatsApp | Meta Cloud API |
| Side-channel | Telegram Bot API |
| IaC | AWS SAM |

---

## Project structure

```
template.yaml                   SAM IaC — all resources
samconfig.toml                  SAM CLI config (dev / prod)
Makefile                        build, deploy, migrate, layer-install

layers/ghost_common/python/
  ssm.py                        SSM loader with in-process cache
  db.py                         psycopg2 connection pool + get_cursor()
  models.py                     all Pydantic v2 models
  whatsapp.py                   Meta Cloud API client

functions/
  webhook_receiver/             GET verify + POST parse → orchestrator
  orchestrator/                 main pipeline controller
  mood_engine/                  mood vector computation (stub → Phase 3)
  timing_engine/                reply now vs delay (stub → Phase 3)
  escalation_detector/          Claude-based sensitivity classifier
  response_generator/           Claude-based reply drafter
  memory_retriever/             pgvector semantic search (stub → Phase 2)
  whatsapp_sender/              sends via Meta Cloud API
  telegram_bot/                 SNS → Telegram with Send/Edit/Skip

migrations/
  versions/001_initial_schema.py    full schema + pgvector + IVFFlat index
```

---

## SSM parameters required

```
/ghost/whatsapp/token
/ghost/whatsapp/phone_number_id
/ghost/whatsapp/verify_token
/ghost/anthropic/api_key
/ghost/telegram/bot_token
/ghost/telegram/chat_id
/ghost/db/connection_string
```

---

## Setup

**1. Install layer dependencies** (Linux-compatible wheels for Lambda)
```bash
make layer-install
```

**2. Build**
```bash
make build
```

**3. Run DB migrations**
```bash
export DATABASE_URL=$(aws ssm get-parameter \
  --name /ghost/dev/db/connection_string \
  --with-decryption --query Parameter.Value --output text)
make migrate
```

**4. Deploy to dev**
```bash
make deploy-dev
```

**5. Deploy to prod**
```bash
make deploy-prod
```

---

## WhatsApp token rotation

Tokens expire every ~24 hours. Update via:

```bash
aws ssm put-parameter \
  --name "/ghost/whatsapp/token" \
  --value "NEW_TOKEN" \
  --type SecureString \
  --overwrite \
  --region eu-west-1
```

Then force cold starts to flush the in-process SSM cache:

```bash
for fn in ghost-webhook-receiver-dev ghost-orchestrator-dev ghost-whatsapp-sender-dev; do
  aws lambda update-function-configuration \
    --function-name $fn \
    --region eu-west-1 \
    --environment "Variables={RELOAD=$(date +%s)}"
done
```

---

## Build phases

**Phase 1 — Skeleton** ✓
Webhook, orchestrator, echo reply, DB schema, Telegram escalation ping, full SAM deploy.

**Phase 2 — Memory** (next)
WhatsApp export ingestion, contact profile builder, real pgvector search, conversation arc state machine.

**Phase 3 — Intelligence**
Real mood engine, real timing engine (SQS delays), Telegram callback handler, confidence scoring, override learning loop.

**Phase 4 — Refinement**
Read receipt logic, proactive outreach, long-delay support (DynamoDB TTL), Next.js dashboard, calendar integration.
