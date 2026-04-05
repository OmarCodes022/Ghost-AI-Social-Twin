# Ghost — AI Social Twin

## Project Overview
Fully autonomous WhatsApp agent that responds as a specific person.
Per-contact memory, dynamic mood, timing intelligence, voice calibration,
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
Makefile                    — build, deploy-dev, deploy-prod, migrate, layer-install, update, db, contact, remember, me, show, contacts, telegram-webhook
scripts/
  admin.py                  — CLI: contact, remember, me, show, contacts subcommands
layers/ghost_common/
  requirements.txt          — psycopg2-binary, pydantic, requests, anthropic
  python/
    ssm.py                  — SSM loader with in-process cache
    db.py                   — psycopg2 connection pool + get_cursor() context mgr
    models.py               — ALL Pydantic models (DB rows + inter-Lambda contracts)
    whatsapp.py             — Meta Cloud API client (send_text_message, mark_read)
functions/
  webhook_receiver/         — GET /webhook verify + POST /webhook parse → invoke orch async
  orchestrator/             — full pipeline: mood → timing → escalation → memory → response → send
  whatsapp_sender/          — sends WhatsApp text via Meta Cloud API
  telegram_bot/             — SNS escalation + /telegram webhook (Send/Edit/Skip callbacks)
  mood_engine/              — signal-based mood vector (time, tier, velocity, weekday)
  timing_engine/            — reply_now / delay_seconds with SQS enqueue
  escalation_detector/      — Claude classifier (strict prompt, confidence >= 0.85 to trigger)
  response_generator/       — Claude claude-sonnet-4-20250514 with full identity + memory prompt
  memory_retriever/         — PostgreSQL full-text search (tsvector); Phase 2 → pgvector cosine
migrations/
  alembic.ini               — points script_location=. (migrations/)
  env.py                    — reads DATABASE_URL env var for connection
  versions/001_initial_schema.py — full schema + pgvector extension + IVFFlat index
tests/unit/                 — placeholder
```

## SSM Parameter Paths
```
/ghost/{env}/whatsapp/token
/ghost/{env}/whatsapp/phone_number_id
/ghost/{env}/whatsapp/verify_token
/ghost/{env}/anthropic/api_key
/ghost/{env}/telegram/bot_token
/ghost/{env}/telegram/chat_id
/ghost/{env}/db/connection_string
```

## WhatsApp Token Management
- Tokens expire every ~24 hours — update via:
  ```bash
  aws ssm put-parameter --name "/ghost/dev/whatsapp/token" --value "NEW_TOKEN" --type SecureString --overwrite --region eu-west-1
  ```
- After updating token, force Lambda cold starts to flush SSM in-process cache:
  ```bash
  for fn in ghost-webhook-receiver-dev ghost-orchestrator-dev ghost-whatsapp-sender-dev; do
    aws lambda update-function-configuration --function-name $fn --region eu-west-1 --environment "Variables={RELOAD=$(date +%s)}"
  done
  ```
- If Meta returns `API access blocked (code 200)`: check app status in Meta Developer Console, not just the token.

## Claude Behaviour Rules
- Never add `Co-Authored-By` or any Claude/Anthropic attribution to git commits
- Never push or commit automatically — always ask the user before committing or pushing

## Key Design Notes
- Lambda layer uses `BuildMethod: python3.12` — SAM installs requirements into `python/`
- `layer-install` Makefile target uses `--platform manylinux2014_x86_64` for Lambda compat
- Alembic migration does ALTER TABLE to cast TEXT → vector(1536) (avoids SQLAlchemy type issues)
- IVFFlat index created with lists=100; tune as knowledge_chunks grows
- Model IDs for LLM: `claude-sonnet-4-20250514`
- Response generator fetches identity chunks directly from DB (contact_phone IS NULL, category='identity') — NOT via memory_retriever, so they're always included regardless of query match
- Orchestrator splits multi-part replies on `\n` and sends each line as a separate WhatsApp message
- Typing indicator simulation: `whatsapp_sender` calls `show_typing()` then sleeps `max(1s, min(6s, len(msg)/15))` before sending. Multi-part replies staggered by `part_index * 4s`.
- **Burst handling**: orchestrator calls `_get_burst_messages()` to collect all user messages since last agent reply. Passes full list to response_generator. First reply part quotes last pending message via WhatsApp `context.message_id` (reply bubble). Supersession check + PostgreSQL advisory lock prevent double-sends when multiple orchestrator invocations race.
- **Deduplication**: `messages.whatsapp_message_id` (unique index, nullable) — if Meta delivers the same webhook twice, second invocation exits early.
- **Escalation threshold**: `confidence >= 0.85` required in orchestrator before routing to Telegram. Escalation detector uses strict prompt — only genuine crisis, real-world action requests, or authenticity challenges.
- **Telegram escalation details**: after Send/Skip/Edit, original notification text is preserved (buttons removed only). Status posted as a new message below.
- `make update` = fast handler-only push (zip + aws lambda update-function-code). Use when only handler.py changed.
- `make deploy-dev` = full SAM build + deploy. Use when template.yaml, layer code, or models.py changed.

---

## Roadmap

### DONE ✓

#### Phase 1 — Skeleton
- [x] WhatsApp webhook verification (GET /webhook)
- [x] Inbound message parsing + logging to DB (webhook_receiver)
- [x] Contact + conversation auto-create on first message
- [x] All messages logged to DB (messages table)
- [x] Echo reply via WhatsApp API end-to-end
- [x] Full RDS schema via Alembic migration (contacts, conversations, messages, mood_states, knowledge_chunks w/ pgvector, escalations)
- [x] SAM template wired: API GW, SQS, SNS, 9 Lambdas, shared Layer
- [x] All secrets in SSM Parameter Store

#### Phase 2 — Memory (partial)
- [x] Knowledge chunks table + full-text search (tsvector) in memory_retriever
- [x] Admin CLI (`scripts/admin.py`) for managing contacts, memories, identity data
- [x] Identity profile seeded (8 knowledge_chunks, category='identity', contact_phone IS NULL)
- [x] Makefile targets: contact, remember, me, show, contacts

#### Phase 3 — Intelligence (partial)
- [x] Mood engine — signal-based vector (time-of-day sinusoid, contact tier warmth, weekday humor, conversation velocity)
- [x] Timing engine — tier-based delay windows, late-night penalty, SQS enqueue
- [x] Orchestrator — full pipeline wired: mood → timing → escalation → memory → response → send
- [x] Orchestrator — SQS delay queue (re-invocation on delay, is_delayed flag skips timing)
- [x] Response generator — Claude API call with full identity + mood + memory + voice prompt
- [x] Response generator — always fetches identity chunks from DB (not query-dependent)
- [x] Multi-message splitting — replies split on `\n`, each line sent as separate WhatsApp message
- [x] Typing indicator simulation — typing bubble + duration proportional to message length + sequential stagger
- [x] Telegram bot — SNS escalation notification with Send/Edit/Skip inline buttons
- [x] Telegram bot — /telegram webhook (API GW route) receiving button callbacks + edited replies
- [x] Telegram bot — Send: DB lookup → whatsapp_sender → resolve escalation
- [x] Telegram bot — Edit: force_reply prompt → edited text → whatsapp_sender → resolve
- [x] Telegram bot — Skip: resolve escalation silently
- [x] Telegram webhook registered with Telegram API
- [x] Escalation detector — real Claude classifier (strict prompt, confidence threshold 0.85)
- [x] Burst detection — orchestrator collects all pending messages, passes to response_generator; reply bubbles last message
- [x] Duplicate webhook deduplication via `messages.whatsapp_message_id`
- [x] Advisory lock prevents double-send on concurrent orchestrator invocations
- [x] Telegram: escalation details preserved after Send/Skip/Edit (buttons removed, status as new message)

---

### REMAINING

#### Phase 2 — Memory (remaining) 🔴 HIGH IMPACT
- [ ] **WhatsApp export ingestion** — parse exported .txt chat history, chunk into knowledge_chunks, store in DB. No real personalization without this. Needed before voice profile extraction.
- [ ] **Voice profile extraction** — per-contact style from chat history: emoji rate, avg message length, formality, vocabulary. Stored as `contacts.voice_profile` JSONB.
- [ ] **pgvector semantic search** — replace tsvector full-text in memory_retriever with `embedding <=> query_vector` cosine similarity. Requires embedding pipeline (Claude or text-embedding model).
- [ ] **Conversation arc tracker** — state machine per conversation: open → flowing → winding_down → dormant. Transitions on message count, recency, reply patterns. Passed to response_generator.

#### Phase 3 — Intelligence (remaining) 🟡 MEDIUM IMPACT
- [ ] **Confidence scoring** — if response_generator confidence < threshold, auto-escalate to Telegram instead of sending. Currently confidence is always 1.0.
- [ ] **Override learning loop** — when you Edit a draft on Telegram, save the edited version as a behavioral knowledge_chunk (`category='behavioral'`). Refines voice over time.
- [ ] **Contact auto-learn** — infer contact name / tone / relationship tier from live conversation and update DB automatically. Currently requires manual `make contact`.

#### Phase 4 — Refinement 🟢 LOWER PRIORITY
- [ ] **Ghost management rules** — intentional read receipts. Mark message as read but don't reply when relationship tier warrants it.
- [ ] **Proactive outreach** — birthday/life event triggers, re-engagement after long silence. Always Telegram-gated before sending.
- [ ] **Long-delay support** — delays >15min currently capped at 900s (SQS max). Need DynamoDB TTL pattern for longer waits.
- [ ] **Dashboard (Next.js)** — conversation feed, mood timeline, override history, per-contact kill switches.
- [ ] **Calendar integration** — Google Calendar API signals meeting-heavy days → mood engine sets low-engagement mode.
- [ ] **Continuous learning** — periodic re-calibration of voice_profile and mood model from accumulated override signals.

---

### Next recommended steps (in order)
1. **WhatsApp export ingestion** — highest leverage, unlocks real memory
2. **pgvector + embeddings** — upgrade memory search quality
3. **Voice profile extraction** — per-contact tone calibration
4. **Conversation arc tracker** — Ghost knows when to wind down
5. **Override learning loop** — Telegram edits saved as behavioral knowledge_chunks
