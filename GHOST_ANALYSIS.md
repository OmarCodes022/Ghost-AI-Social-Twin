# Ghost — Full Technical Reference

> Written at the close of v1. Every file, every function, every decision.
> Use this to understand what was built, why, and what comes next.

---

## Table of Contents

1. [What Ghost is](#1-what-ghost-is)
2. [Architecture overview](#2-architecture-overview)
3. [AWS infrastructure](#3-aws-infrastructure)
4. [Lambda layer -- shared code](#4-lambda-layer----shared-code)
5. [Lambda: webhook_receiver](#5-lambda-webhook_receiver)
6. [Lambda: orchestrator](#6-lambda-orchestrator)
7. [Lambda: whatsapp_sender](#7-lambda-whatsapp_sender)
8. [Lambda: telegram_bot](#8-lambda-telegram_bot)
9. [Lambda: proactive_engine](#9-lambda-proactive_engine)
10. [Database schema](#10-database-schema)
11. [Migrations](#11-migrations)
12. [Scripts](#12-scripts)
13. [Dashboard](#13-dashboard)
14. [Configuration and secrets](#14-configuration-and-secrets)
15. [Known issues and fragile spots](#15-known-issues-and-fragile-spots)
16. [What works well](#16-what-works-well)
17. [Remaining work](#17-remaining-work)
18. [Lessons learned](#18-lessons-learned)

---

## 1. What Ghost is

Ghost is a fully autonomous WhatsApp agent that replies as its owner. It is not a chatbot you hand to users - it is a digital twin that operates on your WhatsApp account without any intervention. Contacts believe they are talking to you.

Core behaviours:
- Reads every inbound WhatsApp text and decides how to reply
- Maintains a system prompt built from: your identity, your mood state, per-contact memories, and conversation history
- Uses Claude (via Strands + Anthropic API) with 9 tools to reason, remember, and write replies
- Sends replies via the Meta Cloud API with realistic typing delays
- Escalates ambiguous situations to a Telegram side-channel for human override (currently disabled, treated as normal reply)
- Sends proactive follow-ups and check-ins autonomously

What Ghost does NOT do:
- Handle voice notes, images, stickers, or any non-text WhatsApp messages (silently skipped)

---

## 2. Architecture overview

```
WhatsApp webhook (Meta Cloud API)
        |
        v
  API Gateway (POST /webhook)
        |
        v
  webhook_receiver Lambda
  - Parses JSON payload
  - Filters to type=text only
  - Fire-and-forget invoke to orchestrator
        |
        v
  orchestrator Lambda                     <- core intelligence
  - Deduplicate (whatsapp_message_id)
  - Block check
  - load_or_create contact + conversation
  - log inbound message
  - collect burst (all unresponded msgs)
  - check if superseded
  - embed burst text (Titan -> Voyage fallback)
  - RAG search (identity + contact chunks via pgvector)
  - build system prompt
  - run Strands agent loop (Claude with 9 tools)
  - check _ctx_terminal (delay / escalate / reply)
  - log agent reply + trace
  - acquire advisory lock
  - invoke whatsapp_sender per reply part
  - send Telegram dev debug trace
        |
        +-- SQS delay queue (if delay_reply called)
        |         |
        |         v
        |   orchestrator Lambda (re-invoked, is_delayed=True)
        |
        +-- whatsapp_sender Lambda (per reply part)
                  - typing indicator
                  - sleep proportional to message length
                  - send via Meta Cloud API
                  - reply bubble (quotes inbound, first part only)

proactive_engine Lambda (EventBridge, every 2h)
  - query quiet candidates (Ghost sent last, no reply 3-24h)
  - query check-in candidates (tier 1-2, no contact 3-30 days)
  - generate reply with Claude (Anthropic SDK directly, not Strands)
  - auto-send tier 1-2, Telegram approval for tier 3+

telegram_bot Lambda (two entry points)
  - SNS: receives escalation events, sends Telegram message with buttons
  - API GW POST /telegram: receives Telegram webhook callbacks
      - Send: invoke whatsapp_sender with proposed reply
      - Edit: force_reply prompt, then await your text
      - Skip: mark escalation resolved, send nothing
      - Text: find pending escalation, send your text
```

---

## 3. AWS infrastructure

All resources defined in `template.yaml` via AWS SAM (CloudFormation superset).

**Stacks:**
- `ghost-dev` (dev environment)
- `ghost-prod` (prod environment)

**Resources:**
- API Gateway (REST) - handles `/webhook` (GET+POST) and `/telegram` (POST)
- 5 Lambda functions (each with its own IAM role)
- 1 Lambda layer (`ghost-common-{env}`) with all shared code
- SQS queue - delay queue for `delay_reply` (max 900s / 15 min visibility)
- SNS topic - escalation events, subscribed by telegram_bot
- RDS PostgreSQL 15 in `eu-west-1` (provisioned separately, not in SAM)
- SSM Parameter Store for all secrets (not in SAM)

**Region:** eu-west-1 (all services)

**Lambda runtimes:** Python 3.12

**IAM permissions for orchestrator:**
- `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream` on Titan and Claude model ARNs
- `lambda:InvokeFunction` on `ghost-whatsapp-sender-{env}`
- `sqs:SendMessage` on the delay queue
- `sns:Publish` on the escalations topic
- `ssm:GetParameter` on `/ghost/*`

**Deployment:**
- `make deploy-dev` - runs `sam build --parallel` then `sam deploy`
- `make update` - fast path: zips `*.py` per function dir, calls `lambda update-function-code` directly (skips SAM build, no layer or template changes)
- Use `make deploy-dev` whenever `template.yaml`, `layers/`, or `models.py` change

---

## 4. Lambda layer -- shared code

Location: `layers/ghost_common/python/`

All 5 Lambda functions import from this layer. Installed with manylinux wheels so the binaries work on Lambda's Amazon Linux 2 environment.

**Install command:**
```bash
pip install -r layers/ghost_common/requirements.txt \
  --target layers/ghost_common/python \
  --platform manylinux2014_x86_64 \
  --implementation cp --only-binary=:all: --python-version 3.12 --upgrade
```

**requirements.txt includes:** psycopg2-binary, pydantic, requests, anthropic, strands-agents

### 4.1 ssm.py

SSM Parameter Store loader with in-process cache.

- `_cache: dict[str, str]` - module-level dict, lives for the Lambda execution environment lifetime
- `get_parameter(name, use_cache=True)` - fetches with `WithDecryption=True`, caches result
- Cache is NEVER invalidated at runtime. To flush: update a Lambda env var (forces cold start)
- The boto3 client itself is also lazily cached in `_client`

**Pattern used everywhere:** `get_parameter(f"/ghost/{env}/something")` where env comes from `os.environ.get("ENV", "dev")`

### 4.2 db.py

psycopg2 connection pool for Lambda.

- `_pool: SimpleConnectionPool | None` - module-level, survives warm invocations
- Pool size: `minconn=1, maxconn=3` - low because Lambda is single-threaded per invocation
- `_ssm_db_param()` - builds `/ghost/{env}/db/connection_string` from env var
- `get_connection()` - context manager; yields connection, commits on success, rolls back on exception, always returns connection to pool; pings with `SELECT 1` first to detect stale idle-timeout connections
- `get_cursor(cursor_factory=RealDictCursor)` - the primary interface everywhere; wraps `get_connection()`, yields cursor, closes cursor in finally

**RealDictCursor** means `cur.fetchone()` returns `{"column": value, ...}` instead of tuples. All DB code in the project relies on this.

### 4.3 models.py

All Pydantic v2 models. Single source of truth for inter-Lambda contracts and DB row shapes.

**Enums (mirror DB ENUM types):**
- `ArcState`: open, flowing, winding_down, dormant
- `MessageRole`: user, agent
- `KnowledgeCategory`: identity, opinion, relationship, behavioral
- `KnowledgeSource`: manual, import, learned
- `EscalationResolution`: sent, edited, skipped, paused

**DB row shapes:**
- `Contact`: phone_number (PK in model, unique in DB), name, relationship_tier (default 3), voice_profile (JSONB dict), last_interaction, interaction_frequency, notes, created_at
- `Conversation`: id (UUID), contact_phone, arc_state, started_at, last_message_at, message_count
- `Message`: id, conversation_id, role, content, sent_at, was_delayed, delay_seconds, mood_state_id, confidence_score, escalated
- `MoodState`: legacy model, not actively used; ghost_state table is what matters now
- `GhostState`: id (always 1), energy (0.6), social_battery (1.0), emotional_load (0.0), availability ("deep"), notes, updated_at
- `KnowledgeChunk`: id, category, content, contact_phone (nullable = identity chunk), created_at, source, similarity_score
- `Escalation`: id, message_id, reason, confidence, telegram_message_id, resolution, resolved_at

**Inter-Lambda contracts:**
- `InboundWhatsAppMessage`: phone_number, message_id (wamid), content, timestamp, message_type, raw_payload
- `OrchestratorEvent`: inbound_message (InboundWhatsAppMessage), is_delayed (bool, default False)
- `WhatsAppSenderRequest`: to_phone_number, message, message_id, part_index (0=first), inbound_message_id (for typing indicator), reply_to_message_id (wamid for reply bubble)
- `TelegramEscalationEvent`: escalation_id, message_id, contact_phone, contact_name, original_message, proposed_reply, reason, confidence

All models use `model_dump(mode="json")` for serialisation so datetime/UUID become JSON strings.

### 4.4 whatsapp.py

Meta Cloud API client. Credentials fetched from SSM on first use, cached module-level.

**Bug (known):** SSM paths are un-scoped: `get_parameter("/ghost/whatsapp/token")` instead of `get_parameter(f"/ghost/{env}/whatsapp/token")`. This means it always reads the unscoped key, regardless of dev/prod environment. To fix: add `env = os.environ.get("ENV", "dev")` and update both paths.

**Graph API version:** v19.0

- `send_text_message(to, text, context_message_id=None)` - POST to `/{phone_number_id}/messages` with type=text. If `context_message_id` provided, adds `"context": {"message_id": ...}` which creates a WhatsApp reply bubble
- `show_typing(inbound_message_id)` - sends `status=read` + `typing_indicator.type=text`. Marks the message as read AND shows the typing indicator. Best-effort, never raises
- `mark_message_read(message_id)` - separate read receipt, same endpoint with `status=read`

---

## 5. Lambda: webhook_receiver

`functions/webhook_receiver/handler.py`

Single entry point. Handles Meta Cloud API webhook verification and inbound message routing.

**GET /webhook - verification handshake:**
Meta sends `hub.mode=subscribe`, `hub.verify_token`, `hub.challenge`. Handler compares verify_token against SSM, returns `hub.challenge` on match. This runs once during initial webhook setup.

**POST /webhook - inbound messages:**
```
body -> json.loads() -> _extract_text_messages() -> for each msg: _invoke_orchestrator_async()
```

`_extract_text_messages()`: walks `body.entry[].changes[].value.messages[]`. Skips anything where `msg.type != "text"` (voice notes, images, stickers, video - all silently skipped with an INFO log). For text messages, builds `InboundWhatsAppMessage` with phone, wamid, content, timestamp.

`_invoke_orchestrator_async()`: invokes `ghost-orchestrator-{env}` with `InvocationType="Event"` (fire-and-forget). The orchestrator runs asynchronously. The webhook handler returns 200 to Meta immediately after dispatching, well within the 500ms window Meta requires (any non-200 triggers retry storms).

**Important:** The lambda client is lazily cached in `_lambda_client`. This is the standard pattern across all Lambdas that call AWS services.

---

## 6. Lambda: orchestrator

`functions/orchestrator/` - 6 files: handler.py, agent.py, tools.py, db_helpers.py, dispatch.py, debug.py

This is the core intelligence of Ghost. Everything else is plumbing.

### 6.1 handler.py

Entry point + pipeline controller.

**`lambda_handler`**: handles two invocation shapes:
- SQS record (delayed re-invoke): `event["Records"]` present, loops and calls `_process` per record body
- Direct invoke (from webhook_receiver): calls `_process(OrchestratorEvent(**event))` directly

**`_BLOCKED = {"201222540825"}`**: module-level set. Numbers here are silently dropped before any DB writes or contact creation. Currently contains one number (the owner's mother).

**`_process` pipeline (in order):**
1. Block check - if `inbound.phone_number in _BLOCKED`: log and return
2. Deduplicate - `already_processed(inbound.message_id)`: checks `messages.whatsapp_message_id` unique index
3. `load_or_create_contact` - gets or creates contact row, updates `last_interaction`
4. `load_or_create_conversation` - gets active (open/flowing) conversation, or creates one
5. `log_message` - inserts inbound message to `messages` table with wamid
6. `get_burst_messages` - fetches all user messages since last agent reply
7. `is_superseded` - if a newer agent reply exists (concurrent orchestrator race), exit
8. `get_identity_chunks` - fallback identity chunks (unfiltered by persona, used if RAG has no embeddings)
9. `get_ghost_state` - reads single-row ghost_state table
10. `run_agent_loop` - runs the Strands agent, returns result dict
11. **Delay branch**: if `result["action"] == "delay"` and not dev: `save_agent_trace`, `enqueue_delay`, return. In dev: falls through and sends immediately
12. **Escalate branch**: if `result["action"] == "escalate"`: DISABLED - converts to normal reply using `draft_reply`
13. **Reply branch**: splits on `\n`, invokes `whatsapp_sender` per part
14. `send_dev_debug` - sends Telegram trace in dev env

**Advisory lock**: `acquire_reply_lock(conversation_id)` - calls `pg_try_advisory_xact_lock(hashtext(conversation_id))`. Advisory lock is scoped to the transaction. Returns True if lock acquired. If another connection holds the same lock, returns False immediately (non-blocking).

**Multi-part reply**: `parts = [p for p in reply.split("\n") if p.strip()]`. Each part is a separate `invoke_whatsapp_sender` call. The first part (i=0) gets `message_id=agent_msg.id` (for DB tracking) and `reply_to_message_id=last_wamid` (WhatsApp reply bubble quoting the inbound). Subsequent parts get neither.

### 6.2 agent.py

The brain. Strands agent with RAG pre-fetch, system prompt construction, and 9 tool wrappers.

**Module-level globals (per-invocation context):**
```python
_ctx_contact: Contact | None        # current contact
_ctx_conversation: Conversation | None
_ctx_tool_calls: list[dict]         # trace accumulator
_ctx_terminal: dict                 # filled by delay_reply / request_human_review
```

These are safe because Lambda is single-threaded per execution. At the start of each `run_agent_loop`, all four are reset.

**Model setup:**
- `_MODEL = "claude-sonnet-4-20250514"` - direct Anthropic API (not Bedrock Claude)
- `_MAX_TOKENS = 1024` - max output tokens per agent reply
- `_anthropic_model: AnthropicModel` - cached globally; built as `AnthropicModel(client_args={"api_key": api_key}, model_id=_MODEL, max_tokens=_MAX_TOKENS)`
- API key from SSM: `/ghost/{env}/anthropic/api_key`

**Bedrock client** (`_bedrock_client`): separate boto3 client for embeddings only (Titan). Lazily cached.

**`embed(text)`:**
1. Tries `amazon.titan-embed-text-v2:0` via Bedrock (1536 dimensions)
2. On `ThrottlingException` or `AccessDeniedException`: falls back to `_embed_voyage(text)` (1024 dimensions)
3. On any other error: logs warning, returns None

**`_embed_voyage(text)`:**
- POSTs to `https://api.voyageai.com/v1/embeddings` with `model=voyage-multilingual-2`
- API key from SSM: `/ghost/{env}/voyage/api_key`
- Returns 1024-dimension embedding

**KNOWN BUG - dimension mismatch:** The DB column `knowledge_chunks.embedding` is `vector(1536)`. Voyage returns 1024-dim. INSERT fails with `"expected 1536 dimensions, not 1024"`. Embeddings from Voyage are silently dropped. Fix: either resize column to 1024 (migration 006) or get Titan quota restored.

**`_embed_and_store(chunk_id, content)`:** embeds then `UPDATE knowledge_chunks SET embedding = %s::vector`. Called by `save_memory` tool after inserting the row. The cast `%s::vector` works because Titan returns exactly 1536 dims. Voyage fails here.

**The 9 Strands tools (defined with `@tool` decorator):**

All tools append to `_ctx_tool_calls` with `{"tool": name, "input": {...}, "output": "summary"}`.

1. **`get_history(limit=20)`** - calls `tool_get_history(conversation_id, limit)`, returns JSON list of `{role, content, sent_at}`. Capped at 50 internally.

2. **`save_memory(content, category)`** - calls `tool_save_memory(content, category, contact_phone)`, then calls `_embed_and_store` on the returned chunk id. Category must be one of: relationship, behavioral, opinion, identity.

3. **`get_contact_profile()`** - calls `tool_get_contact_profile(contact)`, returns JSON with name, tier, voice_profile, notes, last_interaction, interaction_frequency.

4. **`update_contact_profile(field, value)`** - calls `tool_update_contact_profile(phone, field, value)`. Allowed fields: name, relationship_tier, notes.

5. **`get_mood_state()`** - calls `tool_get_mood_state()` which reads ghost_state table. Returns energy, social_battery, emotional_load, availability, notes, updated_at.

6. **`update_mood(aspect, value, reason)`** - calls `tool_update_mood(aspect, value, reason)`. Updates a single aspect of ghost_state. Allowed aspects: energy, social_battery, emotional_load, availability, notes.

7. **`update_conversation_arc(state)`** - calls `tool_update_conversation_arc(conversation_id, state)`. Valid states: open, flowing, winding_down, dormant.

8. **`delay_reply(seconds, reason)`** - writes to `_ctx_terminal`: `{"action": "delay", "seconds": seconds, "reason": reason}`. Returns a string telling Claude to stop. Claude should NOT generate reply text after calling this.

9. **`request_human_review(reason, draft_reply)`** - writes to `_ctx_terminal`: `{"action": "escalate", "reason": reason, "draft_reply": draft_reply}`. Returns a string telling Claude to stop. CURRENTLY DISABLED in handler.py - treated as normal reply using draft_reply.

**`_fetch_rag_context(query_text, contact_phone, voice_profile)`:**
- Embeds `query_text` (the full burst concatenated)
- If embedding succeeds: runs two `rag_search` calls: identity chunks (contact_phone=None) and contact-specific chunks
- If embedding fails (None): falls back to `get_identity_chunks(voice_profile)` which does an unfiltered SQL query
- Returns `(identity_chunks, contact_chunks)`

**RAG search depth:** `_RAG_K = 5` - top-5 identity + top-5 contact chunks.

**`_build_system_prompt`:** constructs a multi-section text:
1. "You are Ghost - an AI standing in for {persona_name}" + never reveal AI
2. Identity chunks (`## {persona_name}'s identity`)
3. Contact chunks (`## What you know about {contact_name}`)
4. Current state: time (UTC day + hour), energy, social_battery, emotional_load, availability, notes
5. Contact info: name/phone, tier
6. If is_delayed: note that the reply was intentionally delayed
7. Conversation style guidelines (be a participant, not a service; ask questions rarely; have opinions)
8. Memory instructions (memories pre-loaded above, save_memory for new info)
9. Tool usage guidelines (update_mood after heavy exchanges, delay_reply / request_human_review stop immediately)
10. Formatting rules: short messages split by newlines, lowercase, minimal punctuation, LANGUAGE rule (infer from last user message, reply in that language even if identity notes are in a different language)

**`_build_initial_message(burst)`:**
- Single message: returns `burst[0]["content"]` directly
- Multiple messages: formats as `[N messages received while you were away]\n[1] ...\n[2] ...`

**`run_agent_loop`:**
1. Resets all module-level context globals
2. Runs `_fetch_rag_context`
3. Uses RAG identity if non-empty, otherwise uses pre-fetched `identity_chunks` fallback
4. Builds system prompt and initial message
5. Creates `Agent(model=_get_anthropic_model(), tools=_TOOLS, system_prompt=..., callback_handler=None)`
6. Calls `agent(initial_message)` - Strands runs the agentic loop until Claude stops calling tools
7. Extracts `reply_text = str(result).strip()`
8. Reads metrics: input_tokens, output_tokens, iterations (via `result.metrics.accumulated_usage`)
9. Checks `_ctx_terminal` - if set, returns delay or escalate action
10. Otherwise returns `{"action": "reply", "reply": reply_text, "tool_calls": [...], "input_tokens": ..., "output_tokens": ..., "iterations": ...}`

### 6.3 tools.py

DB-facing handler functions. Called by the `@tool` wrappers in agent.py. Separated so they can be tested independently.

- `tool_get_contact_profile(contact)` - returns dict from Contact model fields
- `tool_get_history(conversation_id, limit)` - SELECT from messages ORDER BY sent_at DESC LIMIT N, then reverse-sorted ASC. Returns `[{role, content, sent_at}]`
- `tool_save_memory(content, category, contact_phone)` - validates category (defaults to "relationship" if invalid), INSERTs knowledge_chunk with source='learned', returns `{"saved": True, "id": chunk_id}`
- `tool_update_contact_profile(phone, field, value)` - validates allowed fields (name, relationship_tier, notes), runs `UPDATE contacts SET {field} = %s WHERE phone_number = %s`
- `tool_get_mood_state()` - delegates to `get_ghost_state()` from db_helpers, returns dict
- `tool_update_mood(aspect, value, reason)` - validates allowed aspects, runs `UPDATE ghost_state SET {aspect} = %s, updated_at = NOW() WHERE id = 1`
- `tool_update_conversation_arc(conversation_id, state)` - validates against `ArcState` enum values, `UPDATE conversations SET arc_state = %s WHERE id = %s`

**Note on `tool_update_contact_profile`:** Uses f-string interpolation for the column name: `f"UPDATE contacts SET {field} = %s"`. The field is validated against an explicit allowlist `{"name", "relationship_tier", "notes"}` before use, so this is safe from SQL injection.

### 6.4 db_helpers.py

All DB operations for the orchestrator. Each function uses `get_cursor()` context manager.

- **`already_processed(whatsapp_message_id)`** - SELECT from messages WHERE whatsapp_message_id = %s. Returns True if found. Deduplication guard.

- **`is_superseded(conversation_id, my_db_message_id)`** - looks up `sent_at` of the current message, then checks if any agent message in the same conversation was sent after it. Returns True if yes (another orchestrator handled a later message first, this one should abort).

- **`get_burst_messages(conversation_id)`** - gets all user messages in the conversation sent after the most recent agent message. The COALESCE of MAX(sent_at) defaults to epoch so all messages are included if no agent reply exists yet. Returns list of dicts.

- **`acquire_reply_lock(conversation_id)`** - `pg_try_advisory_xact_lock(hashtext(conversation_id))`. Advisory lock is scoped to the transaction. Returns True if lock acquired. If another connection holds the same lock, returns False immediately (non-blocking).

- **`load_or_create_contact(phone_number)`** - SELECT then UPDATE `last_interaction=NOW()`, or INSERT with defaults (relationship_tier=2, interaction_frequency=0.0). Returns Contact model.

- **`load_or_create_conversation(phone_number)`** - SELECT most recent open/flowing conversation for the contact, or INSERT a new one. On existing conversation: UPDATE `last_message_at=NOW(), message_count+1`.

- **`log_message(conversation_id, role, content, whatsapp_message_id=None)`** - INSERT into messages with all defaults. Returns Message model.

- **`get_identity_chunks(voice_profile)`** - SELECT from knowledge_chunks WHERE contact_phone IS NULL AND category='identity' AND persona=%s. The persona comes from `voice_profile.get("persona", "default")`. Returns list of content strings.

- **`rag_search(query_embedding, contact_phone, k=5)`** - pgvector cosine search. If contact_phone is None: searches identity chunks (contact_phone IS NULL, embedding IS NOT NULL). Otherwise: searches contact-specific chunks. Order by `embedding <=> %s::vector`. Returns list of content strings. The `%s::vector` cast is how pgvector accepts the embedding.

- **`get_ghost_state()`** - SELECT from ghost_state LIMIT 1. Returns GhostState model (or default if no row).

- **`save_agent_trace(message_id, conversation_id, contact_phone, result)`** - INSERT into agent_traces. message_id is nullable (delay actions have no outgoing message). Logs tool_calls as JSONB, input/output tokens, iteration count, action string. Wrapped in try/except so trace failures never break the main flow.

### 6.5 dispatch.py

Downstream invocations. Three functions:

- **`enqueue_delay(orch_event, delay_seconds, reason)`** - copies the OrchestratorEvent with `is_delayed=True`, sends to SQS with `DelaySeconds=min(delay_seconds, 900)` (SQS max is 900s / 15 min). The event body is `model_dump_json()`.

- **`invoke_whatsapp_sender(env, to_phone_number, message, message_id, part_index, inbound_message_id, reply_to_message_id)`** - builds `WhatsAppSenderRequest`, invokes `ghost-whatsapp-sender-{env}` with `InvocationType="Event"` (fire-and-forget). The Lambda client is lazily cached.

- **`publish_escalation(contact, original_message, proposed_reply, reason, message_id)`** - builds `TelegramEscalationEvent`, inserts escalation row to DB, publishes to SNS topic. NOT CURRENTLY CALLED - escalation is disabled in handler.py.

### 6.6 debug.py

Sends a Telegram message after every agent loop in dev. Shows a formatted trace.

**`send_dev_debug`:** builds a MarkdownV2 message with:
- Contact name + phone
- The inbound message (truncated to 100 chars)
- Burst count (if > 1 message)
- Tool trace: per tool: emoji + name + input summary + output
- Error list if any tool errored
- Token counts (input + output)
- Ghost state snapshot (energy, battery, load, availability)
- Outcome: delay with duration, or sent reply preview

Uses `_TOOL_EMOJI` dict for per-tool emojis. The `_esc` function escapes MarkdownV2 special characters. Tool input formatting in `_format_tool_input` provides compact one-line summaries per tool.

The bot token and chat_id are read from SSM each call (but cached by ssm.py). Wrapped in try/except - if Telegram fails, it logs a warning and continues.

---

## 7. Lambda: whatsapp_sender

`functions/whatsapp_sender/handler.py`

Sends a single WhatsApp message with realistic human-like timing.

**Constants:**
- `CHARS_PER_SECOND = 15` - typing speed for delay calculation
- `INTER_MESSAGE_GAP = 4` - seconds between sequential reply parts
- `MAX_TYPING_DURATION = 6.0` - max sleep before sending
- `MIN_TYPING_DURATION = 1.0` - min sleep

**Flow for each invocation:**
1. Parse `WhatsAppSenderRequest` from event
2. If `part_index > 0`: sleep `part_index * INTER_MESSAGE_GAP` seconds (so part 1 waits 4s, part 2 waits 8s, etc.) to stagger sequential messages
3. Call `show_typing(inbound_message_id)` - shows "..." bubble and marks message read
4. Sleep `clamp(len(message) / 15, 1.0, 6.0)` seconds - proportional to message length
5. Call `send_text_message(to, message, context_message_id=reply_to_message_id if part_index==0 else None)`
6. Log result including the wamid from Meta's response

**Why fire-and-forget per part:** orchestrator invokes one whatsapp_sender Lambda per reply part, all simultaneously. Each Lambda does its own staggered sleep (INTER_MESSAGE_GAP * part_index) so they naturally serialize from the recipient's perspective.

**Why not a loop in one Lambda:** Lambda has a 15-minute timeout but each individual send is fast. Parallelising them separately keeps the orchestrator unblocked and allows each part's delivery to be tracked independently.

---

## 8. Lambda: telegram_bot

`functions/telegram_bot/handler.py`

Two-in-one Lambda. Handles both SNS escalation notifications and Telegram webhook callbacks.

**Entry point routing:**
- If `event["Records"]` present: SNS event (escalation notification)
- If `event["body"]` present: API Gateway POST from Telegram webhook
- Otherwise: 400

**SNS path - `_handle_sns`:**
Deserialises `TelegramEscalationEvent`, calls `_send_escalation_notification`.

Sends a Telegram message with inline keyboard:
```
[Send]  [Edit]  [Skip]
```
Callback data: `"send:{escalation_id}"`, `"edit:{escalation_id}"`, `"skip:{escalation_id}"`

**Telegram webhook path - `_handle_webhook`:**
Parses the Telegram Update object:
- `callback_query` (button press): routes to `_handle_callback`
- `message` (text from owner): routes to `_handle_message`

**`_handle_callback`:**
Splits `callback_data` on `:` to get action + escalation_id.
- **Send**: calls `_get_escalation`, invokes whatsapp_sender with `proposed_reply`, resolves escalation as "sent", removes buttons, appends "Sent" to Telegram message
- **Skip**: resolves escalation as "skipped", removes buttons
- **Edit**: removes buttons, sends a `force_reply` prompt with the proposed text so owner can reply-edit it inline

**`_handle_message`:**
If owner sends a text message (not a command): finds the most recent unresolved escalation via `_get_pending_escalation`, sends owner's text to WhatsApp, resolves escalation as "edited".

**`_get_escalation`:** JOINs escalations -> messages -> conversations to get proposed_reply and contact_phone by escalation_id.

**`_get_pending_escalation`:** same JOIN but filters WHERE resolved_at IS NULL, orders by sent_at DESC LIMIT 1.

**`_remove_buttons`:** calls `editMessageReplyMarkup` with empty inline_keyboard to strip the buttons from the original message. Then sends a new message with the status suffix (Sent/Skipped/Editing).

**`_esc(text)`:** minimal Markdown escaping for Telegram (underscores, asterisks, backticks).

**CURRENTLY UNUSED:** The escalation path is disabled in handler.py. The telegram_bot Lambda still exists and is fully functional, but the orchestrator never publishes to SNS. `send_dev_debug` in debug.py still sends dev traces directly to Telegram (bypassing SNS/escalations).

---

## 9. Lambda: proactive_engine

`functions/proactive_engine/handler.py`

Scheduled Lambda (every 2h via EventBridge). Autonomously reaches out to contacts.

**Two candidate types:**

1. **Quiet** (`_get_quiet_candidates`): contacts where the last message in their conversation was from Ghost (agent), and that message was sent 3-24h ago with no reply. Conversation arc must be open or flowing. Tier <= 3.

2. **Check-in** (`_get_checkin_candidates`): tier 1-2 contacts with `last_interaction` between 3 and 30 days ago, and no active conversation in the last 24h.

**Processing:** deduplicates by phone, shuffles, takes `MAX_PER_RUN = 3` max per cycle to avoid flooding.

**`_handle_proactive(contact, env)`:**
1. Get conversation history (if quiet trigger - has conv_id) or empty list (if check-in)
2. Get identity chunks for the contact's persona
3. Get recent memories (last 5 by created_at, no RAG - just recency)
4. Call `_generate_proactive_message`
5. If reply starts with "[skip]": log and skip this contact
6. Log the message to DB (as agent role)
7. Route: tier 1-2 auto-send via whatsapp_sender (split on newline), tier 3+ Telegram approval via SNS

**`_generate_proactive_message`:** calls Anthropic SDK directly (`client.messages.create`, not Strands). System prompt includes persona, language rule, trigger instruction (quiet vs check-in), identity chunks, memories, voice profile. History is passed as `messages` array (Claude format: user/assistant). Strips leading assistant turns. If no history: seeds with a fake user message. If history ends with assistant: appends a fake user turn to keep Claude in the right role. max_tokens=200 (short).

**Language rule:** if contact's `voice_profile.preferred_language` is set, uses that. Otherwise: "same language as conversation history, or French if no history."

**Note:** proactive_engine uses `anthropic.Anthropic(api_key=...)` directly, not Strands. This is intentional - proactive messages are simpler, just a single Claude call, no tool loop needed.

**Note 2:** `_get_memory_chunks` in proactive_engine does NOT use RAG (no embeddings). It just returns the 5 most recent knowledge_chunks by created_at. This is a simplification vs the orchestrator's pgvector search.

---

## 10. Database schema

RDS PostgreSQL 15 with pgvector extension. Single database: `ghost`.

### 10.1 contacts

```sql
phone_number          VARCHAR    -- unique per business (actual PK in live DB is id UUID)
name                  VARCHAR
relationship_tier     SMALLINT   NOT NULL DEFAULT 3
voice_profile         JSONB      -- {"avg_message_length":..., "emoji_rate":..., "persona":"default", ...}
last_interaction      TIMESTAMP
interaction_frequency FLOAT      NOT NULL DEFAULT 0.0
notes                 TEXT
created_at            TIMESTAMP  NOT NULL
-- Live DB extra columns (not in migrations):
id                    UUID       PRIMARY KEY (generated)
business_id           UUID
ai_enabled            BOOLEAN
```

**DB vs Migration divergence:** The live DB has `id UUID` as primary key (auto-generated) and extra columns `business_id`, `ai_enabled`. The migration (001) created `phone_number VARCHAR PRIMARY KEY`. This diverged during manual schema changes. Scripts that use `ON CONFLICT (phone_number)` fail because the unique constraint changed. `ingest_whatsapp.py` was fixed with a SELECT-then-UPDATE pattern. `admin.py` `cmd_contact` still has the broken ON CONFLICT and will fail for new contacts.

**voice_profile JSONB fields used:**
- `persona` (string) - which identity profile to use, e.g. "default"
- `persona_name` (string) - display name for the persona, e.g. "Omar"
- `preferred_language` (string) - e.g. "French", "Egyptian Arabic"
- `avg_message_length`, `emoji_rate`, `uppercase_rate`, `formality_score`, `response_style` - from WhatsApp export analysis

### 10.2 conversations

```sql
id               UUID        PRIMARY KEY
contact_phone    VARCHAR     NOT NULL REFERENCES contacts(phone_number)
arc_state        arc_state   NOT NULL DEFAULT 'open'
started_at       TIMESTAMP   NOT NULL
last_message_at  TIMESTAMP   NOT NULL
message_count    INTEGER     NOT NULL DEFAULT 0
```

Arc states: `open` (active), `flowing` (good momentum), `winding_down` (trailing off), `dormant` (no activity). Only `open` and `flowing` conversations are resumed by the orchestrator - the rest trigger new conversation creation.

Indexes: `contact_phone`, `arc_state`

### 10.3 messages

```sql
id               UUID          PRIMARY KEY
conversation_id  UUID          NOT NULL REFERENCES conversations(id)
role             message_role  NOT NULL  -- 'user' or 'agent'
content          TEXT          NOT NULL
sent_at          TIMESTAMP     NOT NULL
was_delayed      BOOLEAN       NOT NULL DEFAULT FALSE
delay_seconds    INTEGER       NOT NULL DEFAULT 0
mood_state_id    UUID          REFERENCES mood_states(id)  -- legacy, unused
confidence_score FLOAT         NOT NULL DEFAULT 1.0
escalated        BOOLEAN       NOT NULL DEFAULT FALSE
whatsapp_message_id VARCHAR    -- added in migration 003, unique index for dedup
```

Index: `conversation_id`

The `whatsapp_message_id` (wamid) unique index is the deduplication mechanism. Meta sends duplicate webhooks sometimes; the orchestrator checks this before any processing.

### 10.4 knowledge_chunks

```sql
id            UUID               PRIMARY KEY DEFAULT gen_random_uuid()
category      knowledge_category NOT NULL  -- identity, opinion, relationship, behavioral
content       TEXT               NOT NULL
embedding     vector(1536)       -- pgvector, NULL if not yet embedded
contact_phone VARCHAR            REFERENCES contacts(phone_number)  -- NULL = identity chunk
created_at    TIMESTAMP          NOT NULL
source        knowledge_source   NOT NULL DEFAULT 'manual'  -- manual, import, learned
persona       VARCHAR(50)        NOT NULL DEFAULT 'default'  -- added in migration 002
```

**Key design:** `contact_phone IS NULL` = identity chunk (about you). `contact_phone = X` = per-contact memory about X.

**RAG:** `embedding <=> query_vector` is the pgvector cosine distance operator. IVFFlat index with `lists=100` covers fast ANN search up to ~1M rows.

**Persona field:** identity chunks are filtered by persona. Contact memories don't use persona (they are all per-contact regardless).

Sources:
- `manual` - added via `make me` or `make remember`
- `import` - added via `make ingest` (WhatsApp export)
- `learned` - added by Claude via `save_memory` tool

**Current state:** Titan embedding is throttled. Voyage fallback produces 1024-dim vectors which fail the 1536-dim column check. Result: embeddings are NULL on most rows. RAG search `WHERE embedding IS NOT NULL` returns empty. Orchestrator falls back to `get_identity_chunks()` which returns ALL identity chunks unfiltered.

### 10.5 mood_states

```sql
id               UUID      PRIMARY KEY DEFAULT gen_random_uuid()
computed_at      TIMESTAMP NOT NULL
energy           FLOAT     NOT NULL DEFAULT 0.5
warmth           FLOAT     NOT NULL DEFAULT 0.5
humor_threshold  FLOAT     NOT NULL DEFAULT 0.5
openness         FLOAT     NOT NULL DEFAULT 0.5
patience         FLOAT     NOT NULL DEFAULT 0.5
signals          JSONB     NOT NULL DEFAULT '{}'
```

Legacy table from an earlier design where mood was computed per-message. Now superseded by `ghost_state`. Not used by any current code.

### 10.6 ghost_state

```sql
id               SERIAL PRIMARY KEY  -- always 1
energy           FLOAT        NOT NULL DEFAULT 0.6
social_battery   FLOAT        NOT NULL DEFAULT 1.0
emotional_load   FLOAT        NOT NULL DEFAULT 0.0
availability     VARCHAR(20)  NOT NULL DEFAULT 'deep'  -- deep / light / minimal
notes            TEXT
updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
```

Single-row table. Read at the start of every orchestrator invocation. Updated by Claude via `update_mood` tool. Manually updatable via `make mood`. The `availability` field is the most impactful: `deep` = full engagement, `light` = casual only, `minimal` = barely present.

### 10.7 escalations

```sql
id                  UUID                  PRIMARY KEY DEFAULT gen_random_uuid()
message_id          UUID                  NOT NULL REFERENCES messages(id)
reason              TEXT                  NOT NULL
confidence          FLOAT                 NOT NULL
telegram_message_id VARCHAR               -- Telegram message_id for button editing
resolution          escalation_resolution -- sent, edited, skipped, paused
resolved_at         TIMESTAMP
```

Indexes: `message_id`

Written when Claude calls `request_human_review` (currently disabled at handler level). Also written by proactive_engine for tier 3+ contacts.

### 10.8 agent_traces

```sql
id              UUID        PRIMARY KEY DEFAULT gen_random_uuid()
message_id      UUID        REFERENCES messages(id) ON DELETE SET NULL  -- nullable (delay actions)
conversation_id UUID        NOT NULL REFERENCES conversations(id) ON DELETE CASCADE
contact_phone   VARCHAR(20) NOT NULL
tool_calls      JSONB       NOT NULL DEFAULT '[]'
input_tokens    INT         NOT NULL DEFAULT 0
output_tokens   INT         NOT NULL DEFAULT 0
iterations      INT         NOT NULL DEFAULT 0
action          VARCHAR(20) NOT NULL DEFAULT 'reply'  -- reply, delay, escalate
created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Indexes: `conversation_id`, `created_at DESC`, `message_id WHERE NOT NULL`

Written after every agent loop. Dashboard reads this to show the collapsible trace block per agent message.

---

## 11. Migrations

Alembic, stored in `migrations/versions/`. Run with `make migrate` (requires `DATABASE_URL` env var).

**001_initial_schema.py** - Full initial schema: pgvector extension, all ENUM types, contacts, mood_states, conversations, messages, knowledge_chunks (with IVFFlat index), escalations. The knowledge_chunks.embedding column is created as TEXT then ALTER'd to vector(1536) using a cast - this workaround avoids Alembic needing to know about the custom type.

**002_add_persona_to_knowledge_chunks.py** - Adds `persona VARCHAR(50) NOT NULL DEFAULT 'default'` to knowledge_chunks. Enables multi-persona support (e.g. different identity profiles for different contacts).

**003_add_whatsapp_message_id.py** - Adds `whatsapp_message_id VARCHAR` to messages + unique index. This is the deduplication key for Meta webhook retries.

**004_ghost_state.py** - Creates `ghost_state` table (single-row persistent mood). Inserts the initial default row on upgrade.

**005_agent_traces.py** - Creates `agent_traces` table for per-reply debug traces. Three indexes including a partial index on message_id.

---

## 12. Scripts

### 12.1 admin.py

CLI for managing Ghost from the terminal. All commands connect to RDS via SSM-fetched DSN.

**`make contact PHONE=... NAME=... TIER=... NOTES=... LANG=... PERSONA=... PERSONA_NAME=...`**
- Uses `ON CONFLICT (phone_number) DO UPDATE` with COALESCE for non-destructive updates
- For `--lang`, `--persona`, `--persona_name`: merges patch into existing `voice_profile` JSONB
- **BROKEN for new contacts** in live DB: the unique constraint is now on `(business_id, phone_number) WHERE business_id IS NOT NULL` (a partial index), not `(phone_number)`. `ON CONFLICT (phone_number)` fails with `InvalidColumnReference`. Fix: use SELECT-then-UPDATE pattern like ingest_whatsapp.py.

**`make remember PHONE=... TEXT=...`**
- Inserts knowledge_chunk with category='relationship', source='manual'
- Calls `_embed_text` (Titan only, no Voyage fallback) to embed immediately
- If embedding succeeds: UPDATE knowledge_chunks SET embedding

**`make me TEXT=... [PERSONA=default]`**
- Same as remember but for identity chunks (contact_phone=NULL)
- Persona from `--persona` arg (defaults to "default")

**`make show PHONE=...`** - prints all contact fields + all knowledge_chunks for the contact

**`make contacts`** - lists all contacts ordered by last_interaction DESC

**`make mood [NOTES=... AVAILABILITY=... ENERGY=... RESET=1]`**
- No args: just displays current ghost_state
- With args: UPDATE ghost_state SET ... WHERE id = 1
- RESET: sets social_battery=1.0, emotional_load=0.0, notes=NULL

**`make send PHONE=... TEXT=...`**
- Manually send a WhatsApp message as Ghost (logged as agent in DB)
- Gets or creates an open/flowing conversation
- Inserts agent message to DB
- Invokes whatsapp_sender Lambda per line of text

**`make proactive PHONES=...,... [DRY_RUN=1]`**
- Generates proactive messages for listed contacts using Claude
- Same Claude call as proactive_engine but run locally
- Dry run mode: generates and prints without sending
- Skips if Claude returns "[skip]"

### 12.2 ingest_whatsapp.py

Ingests a WhatsApp exported `.txt` file into knowledge_chunks.

**Supported formats:**
- iOS: `[DD/MM/YYYY, HH:MM:SS] Sender: message`
- Android: `DD/MM/YYYY, HH:MM - Sender: message`

**`parse_export(path)`:**
Regexes for both formats. Multi-line message continuation: if line starts with space or doesn't match the timestamp pattern and we have a current message, appends to current. Skips system messages via `_SKIP_PATTERNS` (media omitted, deleted messages, etc.).

**`_split_into_sessions(messages)`:**
Groups messages into sessions separated by gaps > `SESSION_GAP = 2h`. Returns list of lists.

**`_session_to_chunks(session, contact_name, my_name)`:**
Splits session into sub-chunks of max `CHUNK_MAX_MSGS = 12` messages. Each chunk is formatted as:
```
[YYYY-MM-DD]
contact_name: their message
me: my message
...
```

**`compute_voice_profile(messages, contact_name, my_name)`:**
Analyses contact's messages (not mine) for:
- `avg_message_length` (chars)
- `emoji_rate` (emojis per message, using unicode range regex)
- `uppercase_rate` (fraction of messages with any uppercase)
- `formality_score` (fraction ending with `.` or starting with uppercase)
- `response_style` ("very short" < 40 chars, "short" < 100, "medium" < 250, "long")
- `total_messages_analysed`

**`ingest(conn, phone, contact_name, chunks, voice_profile, dry_run)`:**
- Upserts contact: SELECT by phone_number, UPDATE if found (COALESCE name, overwrite voice_profile), INSERT if not found
- Inserts each chunk into knowledge_chunks with category='relationship', source='import'
- Does NOT embed (Titan is throttled; would need a separate backfill step)
- Commits on success

**Usage:**
```bash
make ingest FILE=exports/alice.txt PHONE=33744746977 NAME="Alice"
```

---

## 13. Dashboard

`dashboard/` - Next.js 15, App Router, Tailwind CSS, connects directly to RDS.

**Setup:** `make dashboard` fetches DATABASE_URL from SSM and starts `npm run dev` in the dashboard directory. Direct RDS connection via `postgres` npm package (postgres.js).

`lib/db.ts`: `postgres(process.env.DATABASE_URL!, { ssl: {rejectUnauthorized: false}, max: 3, idle_timeout: 20 })` - simple connection pool. SSL required but certificate not verified (RDS self-signed).

### Pages

**`/` (Home):**
- 4 stat cards: contacts count, conversations count, knowledge_chunks count, agent_traces count
- Ghost state panel (MoodPanel component)
- Recent 10 conversations (arc state, last message preview, timestamp)
- Revalidates every 10 seconds (Next.js server-side revalidation)

**`/conversations/[id]` (Conversation view):**
Client component, polls `/api/conversations/${id}` every 5 seconds.
- Header: contact name, arc state, tier, message count
- Message thread with date separators
- Each agent message has a collapsible TraceBlock below it showing tool calls, token counts, iteration count
- Reply bubbles: agent messages right-aligned (violet), user messages left-aligned (zinc)
- Message content split on `\n` to show separate bubble rows
- Compose box at bottom: sends via `/api/send` (POST), auto-scrolls on new messages

**`/contacts/[phone]` (Contact detail):**
Client component.
- Profile editor: name, tier (select 1-5), notes textarea. Saves via PATCH `/api/contacts/${phone}`
- Voice profile: displayed as JSON if present (read-only)
- Memories list with color-coded category badges. Delete button per memory. Add memory form with category selector.
- Conversations list linking to conversation view

**`/mood` (Ghost state editor):**
Client component.
- Current state display bars (energy violet, social_battery blue, emotional_load orange)
- Edit form: sliders for the three numeric fields, select for availability, textarea for notes
- Saves via POST `/api/mood`

**TraceBlock component:** collapsible section under each agent message. Shows each tool call with name, input summary, output. Token and iteration counts.

**MoodPanel component:** non-interactive display of ghost state (bars + availability badge + notes).

---

## 14. Configuration and secrets

All secrets in SSM Parameter Store, `SecureString` type. Path convention: `/ghost/{env}/{category}/{key}`.

| Path | Purpose |
|---|---|
| `/ghost/{env}/whatsapp/token` | Meta Cloud API bearer token (expires ~24h, must rotate regularly) |
| `/ghost/{env}/whatsapp/phone_number_id` | Meta phone number ID for the API |
| `/ghost/{env}/whatsapp/verify_token` | Static token for webhook verification handshake |
| `/ghost/{env}/anthropic/api_key` | Anthropic API key for Claude + proactive_engine |
| `/ghost/{env}/voyage/api_key` | Voyage AI API key for embedding fallback |
| `/ghost/{env}/telegram/bot_token` | Telegram bot token for escalations + dev debug |
| `/ghost/{env}/telegram/chat_id` | Your Telegram chat ID |
| `/ghost/{env}/db/connection_string` | Full PostgreSQL DSN including password |

**Token rotation (WhatsApp):**
Meta tokens expire every ~24h. Update SSM then force Lambda cold starts:
```bash
aws ssm put-parameter --name "/ghost/dev/whatsapp/token" --value "NEW_TOKEN" \
  --type SecureString --overwrite --region eu-west-1
for fn in ghost-webhook-receiver-dev ghost-orchestrator-dev ghost-whatsapp-sender-dev; do
  aws lambda update-function-configuration --function-name $fn --region eu-west-1 \
    --environment "Variables={RELOAD=$(date +%s)}"
done
```

**SSM caching:** ssm.py caches parameter values in memory for the Lambda execution environment lifetime. The only way to force a re-read is a cold start (new execution environment). This is intentional for performance.

**Env vars on Lambda:**
- `ENV` = "dev" or "prod" (set by SAM template via `--parameter-overrides Env=dev`)
- `LOG_LEVEL` = "INFO" (default)
- `DELAY_QUEUE_URL` = SQS queue URL (set by SAM)
- `ESCALATIONS_TOPIC_ARN` = SNS topic ARN (set by SAM)
- `AWS_REGION` / `AWS_DEFAULT_REGION` = eu-west-1

---

## 15. Known issues and fragile spots

### 15.1 Embedding dimension mismatch (CRITICAL)

Titan returns 1536-dim vectors. The column is `vector(1536)`. Titan is throttled.

Voyage fallback returns 1024-dim vectors. INSERT fails with: `"expected 1536 dimensions, not 1024"`.

Result: no new embeddings are stored. `rag_search` returns empty (all WHERE embedding IS NOT NULL rows return nothing). Orchestrator falls back to unfiltered `get_identity_chunks()` which loads ALL identity chunks in insertion order regardless of relevance.

**Fix options:**
1. Get Titan quota restored (no code change needed)
2. Resize column to 1024 via migration, switch `_embed_voyage` to primary (no Titan calls)
3. Migrate to Cohere Embed v3 via Bedrock (best long-term, when account access enabled)

### 15.2 admin.py cmd_contact ON CONFLICT bug

`ON CONFLICT (phone_number) DO UPDATE` fails because `phone_number` is no longer the primary key. The unique constraint is now on `(business_id, phone_number) WHERE business_id IS NOT NULL`.

Affects: `make contact PHONE=... NAME=...` for new contacts.

`ingest_whatsapp.py` already fixed. `admin.py` still broken.

### 15.3 whatsapp.py un-scoped SSM paths

`_get_token()` reads `/ghost/whatsapp/token` (no `{env}`) instead of `/ghost/{env}/whatsapp/token`. Same for phone_number_id.

Means dev and prod share the same WhatsApp token, which makes multi-env testing awkward and means the SSM parameter name diverges from the documented convention.

### 15.4 No embeddings on identity chunks

Existing identity chunks (added via `make me`) have `embedding = NULL`. When RAG search is eventually fixed (embedding dimension resolved), these chunks won't be found by semantic search.

Requires a backfill script: for each identity chunk, call `embed()` and UPDATE.

### 15.5 SQS delay limit (15 minutes)

`delay_reply` caps at 900 seconds. If Claude wants to wait "a few hours" to reply, the architecture cannot support it. A DynamoDB TTL pattern would be needed for longer delays.

### 15.6 Dev delay bypass

In dev, `delay_reply` results fall through to immediate send. This is intentional for testing, but means delay behaviour is untested in dev. Could cause surprises when deploying to prod.

### 15.7 Proactive engine uses no RAG

`_get_memory_chunks` returns last 5 chunks by created_at, not by relevance. Proactive messages might miss the most relevant memories. The orchestrator uses full pgvector search; proactive_engine does not.

### 15.8 Escalation is disabled

`request_human_review` in handler.py converts to a normal reply using `draft_reply`. This means Ghost never escalates - it always sends, even for edge cases it flagged as needing human review. This was intentional while debugging but should be revisited for production use.

### 15.9 Potential double-send on advisory lock failure

`acquire_reply_lock` uses `pg_try_advisory_xact_lock` which is scoped to the transaction. If the lock is released (transaction ends) before `invoke_whatsapp_sender` completes, a concurrent invocation could also acquire the lock and send. The lock scope and the invocation are not atomic.

---

## 16. What works well

**The agent loop quality:** Claude + Strands works very well. The 9-tool design is clean. The system prompt structure (identity -> contact memories -> state -> contact info -> guidelines) gives Claude good context without overloading it. Replies are natural and context-aware.

**Burst message collection:** collecting all unresponded user messages and presenting them as a single coherent burst is the right design. Claude sees the full context in one pass rather than reasoning about each message individually.

**Advisory lock + superseded check:** the concurrency handling is solid. `pg_try_advisory_xact_lock` prevents double-sends on race conditions without needing distributed locks. `is_superseded` prevents stale orchestrators from overwriting newer replies.

**Typing simulation:** the CHARS_PER_SECOND + INTER_MESSAGE_GAP pattern makes Ghost feel genuinely human. Recipients see "typing..." for a realistic duration, then messages arrive with natural gaps.

**Reply bubble (context_message_id):** quoting the inbound message on the first reply part makes Ghost feel present in the conversation rather than responding into a void.

**Module-level context pattern:** using module-level globals (`_ctx_contact`, etc.) for per-invocation context is elegant given Lambda's single-threaded execution model. Avoids threading complexity while keeping tool wrappers clean.

**Dev debug trace via Telegram:** the `send_dev_debug` block in debug.py gives real-time visibility into every invocation without having to trawl CloudWatch. Seeing tool calls, token counts, and the reply in Telegram is extremely useful.

**Dashboard:** the conversation view with live polling and collapsible trace blocks is the primary debugging tool. Being able to see exactly what tools Claude called, with what inputs, and what it output, makes iteration fast.

**SSM + connection pool pattern:** caching SSM values and DB connections across warm invocations significantly reduces latency. First cold start is slow; subsequent warm invocations skip SSM lookups and pool connection establishment.

**Pydantic v2 models:** using Pydantic for all inter-Lambda contracts catches shape errors early and makes serialisation/deserialisation trivial.

---

## 17. Remaining work

**Embedding (BLOCKING):**
- Resolve Titan throttling or resize column to 1024 for Voyage
- Backfill embeddings on all existing identity chunks
- Long-term: migrate to Cohere Embed v3 via Bedrock (multilingual, 1024 dims, IAM auth)

**Agent quality:**
- Confidence-based escalation: re-enable `request_human_review` path, add actual confidence scoring
- Override learning loop: when owner edits a Telegram escalation, save the edited version as a `behavioral` knowledge_chunk + embed it
- Long-delay support: DynamoDB TTL pattern for delays > 15 minutes

**Operational:**
- Fix `admin.py` `cmd_contact` ON CONFLICT bug
- Fix `whatsapp.py` un-scoped SSM paths
- Rotate DB password (was exposed in a chat session)

**Data:**
- WhatsApp export ingestion for remaining contacts
- Voice profile backfill from existing chat history
- Conversation arc state machine - automated transitions (e.g. auto-dormant after 30 days no activity)

**Features:**
- Calendar integration: meeting-heavy days -> low engagement mode, set availability automatically
- Long-term memory summarisation: as knowledge_chunks grow, summarise older ones to avoid context bloat

---

## 18. Lessons learned

**The Strands SDK is new and has rough edges.** The critical bug (line 353 calling `_get_bedrock_model()` which didn't exist) was a leftover from a refactor that switched from BedrockModel to AnthropicModel. The SDK worked fine once the model was correctly wired up - Ghost went from silent to responding in seconds.

**Lambda module-level state is powerful.** Using module-level globals for per-invocation context (`_ctx_contact`, `_ctx_terminal`, etc.) feels like it should be dangerous but works reliably because Lambda only runs one request at a time. The pattern avoids threading complexity and keeps tool wrappers simple.

**pgvector is worth it, but dimension management matters.** The IVFFlat index + cosine operator is fast and effective. But having two embedding models with different dimensions (1536 vs 1024) created a silent failure mode where embeddings stopped being stored. Always validate that stored embeddings match the column dimension.

**SSM credential caching is necessary.** Without it, every DB operation would involve an SSM call. With it, credentials are fetched once per Lambda execution environment and cached. The tradeoff (cache invalidation requires cold starts) is acceptable for secrets that rotate infrequently.

**The burst message design is correct.** Collecting all pending messages before running Claude means the agent has full context. If you processed each message as it arrived, Claude would be writing replies without knowing the next message was already queued.

**Telegram as dev debug channel works extremely well.** Real-time trace notifications in Telegram mean you can test Ghost just by sending yourself a WhatsApp message and immediately seeing what Claude reasoned, what tools it called, and what it replied - without opening CloudWatch.

**Escalation should be a last resort.** The proactive decision to disable escalation in dev (and convert to normal replies) was the right call for initial testing. With escalation enabled, any edge case becomes an interruption. Better to have Ghost try its best and review replies in the dashboard.

**The dashboard is essential.** The conversation view with agent traces is the primary way to understand why Ghost said what it said. Without it, debugging requires reading CloudWatch JSON logs, which is slow. Building this early was the right call.

**Keep the layer requirements minimal.** `strands-agents` is large. Every addition to `requirements.txt` adds to cold start time and layer size. Only add packages that are truly shared across multiple Lambdas. Function-specific packages should be inlined where possible.
