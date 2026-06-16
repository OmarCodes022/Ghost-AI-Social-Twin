# Ghost — AI Social Twin

## Project Overview
Fully autonomous WhatsApp agent that responds as a specific person.
Per-contact memory (RAG via pgvector), dynamic mood, timing intelligence,
escalation detection, Telegram side-channel for human override.

## Key Conventions
- Prefix: `ghost`, Envs: `dev` / `prod`, Region: `eu-west-1`, Python 3.12
- Resource naming: `ghost-{resource}-{env}` (e.g. `ghost-orchestrator-dev`)
- All secrets via SSM Parameter Store (`/ghost/{env}/**`)
- All inter-Lambda contracts typed with Pydantic v2
- Structured JSON logging — no print() anywhere
- DB: RDS PostgreSQL 15 + pgvector; connection pool via `db.get_cursor()`

## File Map
```
template.yaml               — SAM IaC (API GW, SQS, SNS, all Lambdas, Layer)
samconfig.toml              — SAM CLI config (dev / prod stacks)
Makefile                    — all commands (see below)
layers/ghost_common/
  requirements.txt          — psycopg2-binary, pydantic, requests, anthropic, strands-agents
  python/
    ssm.py                  — SSM loader with in-process cache
    db.py                   — psycopg2 connection pool + get_cursor() context mgr
    models.py               — ALL Pydantic models (DB rows + inter-Lambda contracts)
    whatsapp.py             — Meta Cloud API client (send_text_message, mark_read)
functions/
  webhook_receiver/         — GET /webhook verify + POST /webhook parse → invoke orch async
  orchestrator/
    handler.py              — entry point + _process pipeline (dedupe, burst, lock, dispatch)
    agent.py                — Strands Agent + BedrockModel, embed(), RAG pre-fetch, @tool wrappers
    tools.py                — DB-facing tool handler functions (called by @tool wrappers in agent.py)
    db_helpers.py           — all DB ops: contact, conversation, message, trace, rag_search()
    dispatch.py             — SQS / Lambda / SNS invocations
    debug.py                — Telegram dev trace block
  whatsapp_sender/          — sends via Meta Cloud API + typing simulation
  telegram_bot/             — SNS escalation + Send/Edit/Skip callbacks
  proactive_engine/         — scheduled follow-ups + check-ins
migrations/
  versions/001_initial_schema.py  — full schema + pgvector + IVFFlat index
  versions/002_add_persona_to_knowledge_chunks.py
  versions/003_add_whatsapp_message_id.py
  versions/004_ghost_state.py     — persistent mood state table
  versions/005_agent_traces.py    — per-reply agent loop trace table
scripts/
  admin.py                  — CLI: contact, remember, me, show, contacts, mood, send, proactive
dashboard/                  — local Next.js debug UI (direct RDS connection)
  app/page.tsx              — home: stats + ghost state + recent convos
  app/conversations/[id]/page.tsx — messages + expandable agent traces
  app/contacts/[phone]/page.tsx   — contact editor + memory manager
  app/mood/page.tsx         — ghost state editor
```

## How the Agent Works

Each inbound message triggers:
1. **Embed** incoming burst text → Titan Text Embeddings v2 via Bedrock (fallback: Voyage)
2. **RAG search** — pgvector cosine `<=>` over `knowledge_chunks.embedding`, top-5 identity chunks + top-5 contact chunks
3. **System prompt** built with: persona identity, contact memories, mood state, contact profile
4. **Strands `Agent(model=BedrockModel(...), tools=[...])` runs** — Claude calls tools as needed, returns reply
5. **Dispatch** — reply split on `\n`, each part sent as separate WhatsApp message

**Embeddings are stored at write time**: `save_memory` tool and `make remember` / `make me` both call `embed()` and update `knowledge_chunks.embedding` immediately.

## Agent Tools (9)

| Tool | Purpose |
|---|---|
| `get_history` | Fetch recent conversation messages |
| `save_memory` | Write a new knowledge_chunk + embed it |
| `get_contact_profile` | Name, tier, voice_profile, notes |
| `update_contact_profile` | Update name / tier / notes |
| `get_mood_state` | Read ghost_state |
| `update_mood` | Update energy / battery / load / availability |
| `delay_reply` | Exit loop, re-invoke via SQS after N seconds |
| `request_human_review` | Escalate to Telegram with draft |
| `update_conversation_arc` | Mark conversation open / flowing / winding_down / dormant |

`search_memories` does not exist — do not reintroduce it. Memory is pre-injected via RAG.

## Models

- **Claude**: `anthropic.claude-sonnet-4-20250514-v1:0` via Bedrock (`BedrockModel`) — IAM auth, no API key
- **Embeddings**: `amazon.titan-embed-text-v2:0` via Bedrock, 1536 dims — matches `knowledge_chunks.embedding vector(1536)`
- **Embedding fallback**: Voyage `voyage-multilingual-2` (1024 dims) if Titan returns AccessDenied

## SSM Parameter Paths
```
/ghost/{env}/whatsapp/token
/ghost/{env}/whatsapp/phone_number_id
/ghost/{env}/whatsapp/verify_token
/ghost/{env}/voyage/api_key          ← only needed if Titan Bedrock access is blocked
/ghost/{env}/telegram/bot_token
/ghost/{env}/telegram/chat_id
/ghost/{env}/db/connection_string
```

## IAM: Orchestrator Lambda needs
- `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream` on both Titan and Claude model ARNs
- `lambda:InvokeFunction` on whatsapp-sender
- `sqs:SendMessage` on delay queue
- `sns:Publish` on escalations topic
- `ssm:GetParameter` on `/ghost/*`

## Makefile Commands
```bash
make layer-install           # install layer deps (manylinux wheels for Lambda)
make deploy-dev              # SAM build + deploy to dev
make update                  # fast handler-only push (zip *.py + lambda update-function-code)
make migrate                 # run Alembic migrations (requires DATABASE_URL env var)
make dashboard               # fetch DATABASE_URL from SSM + start Next.js dev server

make contact PHONE=... NAME="Alice" TIER=1
make remember PHONE=... TEXT="Has a dog called Max"
make me TEXT="I hate small talk"
make mood
make send PHONE=... TEXT="yo"
make proactive PHONES=...
make db                      # live psql session against dev DB
```

## Key Design Notes

- **Burst handling**: `get_burst_messages()` collects all user messages since last agent reply. All passed as single initial message to the Strands agent. First WhatsApp reply quotes the last pending message (reply bubble).
- **Deduplication**: `messages.whatsapp_message_id` unique index — duplicate Meta webhooks exit early.
- **Advisory lock**: `pg_try_advisory_xact_lock(hashtext(conversation_id))` prevents double-send on concurrent orchestrator invocations.
- **Terminal tools**: `delay_reply` and `request_human_review` write to a module-level `_ctx_terminal` dict and tell Claude to stop. After `agent()` returns, handler checks `_ctx_terminal` and routes accordingly.
- **RAG fallback**: if no embeddings exist yet (legacy rows), `rag_search()` returns empty and handler falls back to `get_identity_chunks()` (unfiltered identity chunks by persona).
- **Multi-part replies**: reply split on `\n`, each line sent as separate WhatsApp message with staggered typing delay.
- **WhatsApp token rotation**: tokens expire ~24h; update via `aws ssm put-parameter`, then force cold starts with a `RELOAD` env var update on all affected Lambdas.
- **`make update`** zips all `*.py` in the function directory — use after any Python file change. Use `make deploy-dev` when `template.yaml`, layer, or `models.py` changed.

## Remaining Work

- **Backfill embeddings** on existing identity chunks — currently none have embeddings, so RAG always falls back to `get_identity_chunks()`. Run `embed()` on all existing rows to activate RAG for identity context.
- **Migrate to Cohere via Bedrock** (best long-term embedding path) — once Cohere Embed v3 multilingual is enabled on the AWS account: (1) run migration `006_resize_embedding_cohere.py` to `ALTER COLUMN embedding TYPE vector(1024)` + recreate IVFFlat index, (2) replace `_embed_voyage()` in `agent.py` with a Bedrock Cohere call (IAM auth, no extra API key), mirror same change in `scripts/admin.py`, (3) backfill all existing `knowledge_chunks` rows. Until then, Voyage (`/ghost/{env}/voyage/api_key` in SSM) is the active embedding fallback.
- **WhatsApp export ingestion** — parse `.txt` chat exports, chunk into `knowledge_chunks`, embed and store.
- **Voice profile extraction** — per-contact style calibration from chat history (emoji rate, avg length, formality).
- **Override learning loop** — Telegram edits → save as `behavioral` knowledge_chunk + embed.
- **Confidence-based escalation** — auto-escalate when confidence < threshold (currently always 1.0).
- **Long-delay support** — SQS max is 15 min; need DynamoDB TTL pattern for longer delays.
- **Calendar integration** — meeting-heavy days → low-engagement mode.
