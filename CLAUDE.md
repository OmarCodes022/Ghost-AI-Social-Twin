# CLAUDE.md

This repo is Ghost, an AWS SAM WhatsApp agent that replies as the owner with memory, mood, and Telegram review.

## Current Architecture

- `functions/webhook_receiver/handler.py` handles Meta webhook verification and inbound WhatsApp text payloads, then invokes `ghost-orchestrator-{env}` asynchronously.
- `functions/orchestrator/handler.py` is the core pipeline: dedupe, contact/conversation loading, burst collection, agent execution, delay/escalation/reply dispatch, trace logging.
- `functions/orchestrator/agent.py` runs a Strands `Agent` with Claude `claude-sonnet-4-20250514`.
- RAG is pre-fetched before the agent call: incoming burst text is embedded with Titan Text Embeddings v2, falling back to Voyage, then searched against `knowledge_chunks.embedding` via pgvector.
- `functions/orchestrator/tools.py` contains the DB-facing tool handler functions. Strands `@tool` wrappers live in `agent.py`.
- `functions/telegram_bot/handler.py` handles SNS escalations and Telegram Send/Edit/Skip callbacks.
- `functions/whatsapp_sender/handler.py` sends WhatsApp messages with typing simulation and reply-bubble support.
- `functions/proactive_engine/handler.py` runs scheduled follow-ups and check-ins.
- `dashboard/` is a local Next.js debug UI connected directly to Postgres.

## Important Commands

```bash
make layer-install
make deploy-dev
make update
make migrate
make dashboard
make db
```

Admin helpers:

```bash
make contact PHONE=... NAME="Alice" TIER=1
make remember PHONE=... TEXT="Has a dog called Max"
make me TEXT="I hate small talk"
make mood
make send PHONE=... TEXT="yo"
make proactive PHONES=...
```

## Secrets

SSM parameters are environment-scoped:

```text
/ghost/{env}/whatsapp/token
/ghost/{env}/whatsapp/phone_number_id
/ghost/{env}/whatsapp/verify_token
/ghost/{env}/anthropic/api_key
/ghost/{env}/voyage/api_key
/ghost/{env}/telegram/bot_token
/ghost/{env}/telegram/chat_id
/ghost/{env}/db/connection_string
```

## Notes For Future Agents

- Do not reintroduce `search_memories`; semantic memory retrieval is now preloaded in `agent.py` through pgvector.
- New memories should be embedded when saved so they participate in future RAG.
- Keep Lambda layer dependencies in `layers/ghost_common/requirements.txt`.
- Be careful with the dirty worktree. Several files may already contain local in-progress changes.
- The dashboard trace UI reads `agent_traces.tool_calls`; keep tool call names and summaries stable when possible.
