# 09 — Database Schema

## Purpose

This document defines every table in Ghost v2, in the order they were introduced during design, along with who reads and writes each one. All tables live in a single RDS PostgreSQL 15 instance with the `pgvector` extension, in `eu-west-1`, accessed by every Lambda through RDS Proxy for connection pooling (see `13_INFRASTRUCTURE.md`).

A guiding rule applies throughout: **Layer 1 (pulse) never computes signals — it only reads clean signals that something else already computed and stored** (Principle 4, `00_OVERVIEW.md`). The "Who writes" column for every table should be read with this rule in mind — if pulse ever appears as a writer, it is writing pure-math derivations (like score accumulation), never anything requiring understanding.

---

## Table 1 — `contacts`

The foundational profile. One row per person Ghost knows.

```sql
phone_number           VARCHAR PRIMARY KEY   -- E.164 format
name                    VARCHAR
relationship_tier       SMALLINT DEFAULT 3   -- 1=closest, 5=stranger
language_primary        VARCHAR
language_secondary      VARCHAR
texting_style            JSONB                -- length, speed, emoji rate, formality
personality_summary      TEXT
current_life_situation   TEXT
trust_level              FLOAT DEFAULT 0.5
risk_level               FLOAT DEFAULT 0.5
relationship_goal        TEXT
created_at               TIMESTAMP
updated_at                TIMESTAMP
```

**Who writes:** onboarding pipeline (`12_ONBOARDING_CONTACTS.md`), Agent 3 (updates over time), Ghost directly via SQL tool
**Who reads:** context assembly (every active chat and heartbeat call), pulse (every cycle)

---

## Table 2 — `contact_state`

Volatile, frequently-updated signals. Kept separate from `contacts` specifically because it changes on a completely different cadence (continuously vs. rarely). One row per contact, always current.

```sql
contact_phone             VARCHAR FK contacts PRIMARY KEY
current_attitude_score    FLOAT
attitude_trend            FLOAT     -- positive = warming, negative = cooling
attitude_trend_duration   INTEGER   -- consecutive conversations this trend has held
last_interaction_at        TIMESTAMP
last_interaction_role       VARCHAR  -- 'ghost' | 'contact'
baseline_frequency           FLOAT    -- average hours between interactions
conversation_quality_avg     FLOAT
unanswered_message_flag      BOOLEAN
unanswered_since              TIMESTAMP
pulse_score                   FLOAT    -- current accumulated weighted score
pulse_score_updated_at        TIMESTAMP
last_heartbeat_action          TEXT
last_heartbeat_at               TIMESTAMP
updated_at                       TIMESTAMP
```

**Who writes:** Agent 1 (attitude shift signal on every incoming message), Agent 3 (full update after every chat close), pulse (score accumulation, pure math), heartbeat (last action taken)
**Who reads:** pulse (every cycle — this is pulse's primary read target), context assembly, heartbeat

---

## Table 3 — `conversations`

One row per conversation session.

```sql
id                    UUID PRIMARY KEY
contact_phone          VARCHAR FK contacts
state                  VARCHAR   -- 'open' | 'closed'
started_at              TIMESTAMP
closed_at                TIMESTAMP
message_count             INTEGER
quality_score              FLOAT
emotional_tone              TEXT
close_condition             JSONB   -- structured condition, see 05_CONDITION_SYSTEM.md
summary                       TEXT    -- written by Agent 3 after close
unresolved_threads             JSONB   -- extracted by Agent 3
updated_at                       TIMESTAMP
```

**Who writes:** active chat flow (opens conversations, Ghost sets `close_condition`), pulse (marks `closed` when condition resolves), Agent 3 (writes `summary` and `unresolved_threads`)
**Who reads:** context assembly (conversation history), Agent 3, pulse

---

## Table 4 — `messages`

Every message ever sent or received.

```sql
id                      UUID PRIMARY KEY
conversation_id           UUID FK conversations
contact_phone               VARCHAR FK contacts
role                          VARCHAR   -- 'ghost' | 'contact'
content                        TEXT
language                        VARCHAR
sent_at                           TIMESTAMP
was_deferred                       BOOLEAN
defer_duration                       INTEGER
whatsapp_message_id                   VARCHAR  -- nullable; outbound messages have none
```

**Who writes:** active chat flow (inbound), `ghost-whatsapp-sender` (outbound)
**Who reads:** context assembly (conversation history), Agent 3, Agent 1

---

## Table 5 — `defer_conditions`

Every conscious defer Ghost has ever set, active or resolved. The backbone of the condition system (`05_CONDITION_SYSTEM.md`).

```sql
id                  UUID PRIMARY KEY
contact_phone         VARCHAR FK contacts
condition               JSONB    -- structured condition object
reason                    TEXT     -- Ghost's own stated reasoning
created_at                 TIMESTAMP
expires_at                   TIMESTAMP  -- optional hard expiry
resolved_at                    TIMESTAMP
status                           VARCHAR  -- 'active' | 'resolved' | 'expired'
```

**Who writes:** Ghost (active chat flow or heartbeat flow)
**Who reads:** pulse (evaluated mechanically every cycle)

---

## Table 6 — `ghost_state`

Ghost's inner life. A single row, always current — this is deliberately not historized in this table (history of *reasoning* lives in `ghost_reflections`, table 11).

```sql
id                      INTEGER PRIMARY KEY  -- always 1
mood                       TEXT
social_battery               FLOAT    -- 0.0 to 1.0
emotional_load                  FLOAT
current_focus                     TEXT
whats_on_mind                       TEXT
period_description                    TEXT   -- e.g. "going through a tough week"
updated_at                              TIMESTAMP
updated_by                                 VARCHAR  -- 'ghost' | 'heartbeat' | 'manual'
```

**Who writes:** Ghost (any flow, via SQL tool)
**Who reads:** context assembly (every single call, across every flow), pulse (mood is one of the scoring signals)

---

## Table 7 — `ghost_intentions`

Ghost's self-set relationship goals and decisions, distinct from the static `relationship_goal` field in `contacts` — this table tracks the *active, evolving* intentions Ghost forms on his own.

```sql
id                  UUID PRIMARY KEY
contact_phone         VARCHAR FK contacts  -- nullable, for global intentions
intention               TEXT
reason                    TEXT
created_at                  TIMESTAMP
acted_on_at                    TIMESTAMP
status                           VARCHAR  -- 'active' | 'completed' | 'abandoned'
```

**Who writes:** Ghost (any flow)
**Who reads:** pulse (an active intention is one scoring signal), heartbeat (context), context assembly

---

## Table 8 — `memories`

Everything Ghost remembers, factual or episodic. The RAG source table (see `03_MEMORY_SYSTEM.md`).

```sql
id                     UUID PRIMARY KEY
contact_phone            VARCHAR FK contacts  -- nullable, for global/identity memories
category                   VARCHAR   -- 'fact' | 'emotional' | 'pattern' | 'negative' |
                                       -- 'inside_joke' | 'observation' | 'identity' | 'behavioral'
content                      TEXT
language                       VARCHAR
embedding                        vector(1024)  -- Voyage-3 multilingual, fixed dimensionality
importance                          FLOAT
created_at                            TIMESTAMP
created_by                               VARCHAR  -- 'agent3' | 'ghost' | 'onboarding'
source_conversation                        UUID FK conversations  -- nullable
```

**Who writes:** Agent 3 (after every chat close), Ghost (directly, via SQL tool, self-authored notes), onboarding pipelines (both Omar's and contacts')
**Who reads:** Ghost (via the RAG tool, his own initiative — never auto-injected)

Note: this single table holds both per-contact episodic memory **and** Omar's own deep identity content (life story, interests, opinions) tagged with `category = 'identity'` and `contact_phone = NULL`. They share the table because they share the same retrieval mechanism (multilingual RAG); they differ only in scope.

---

## Table 9 — `life_events`

Known dates and events per contact.

```sql
id                  UUID PRIMARY KEY
contact_phone         VARCHAR FK contacts
event_type              VARCHAR  -- 'birthday' | 'exam' | 'trip' | 'interview' |
                                   -- 'anniversary' | 'custom'
description               TEXT
event_date                  DATE
lookahead_days                 INTEGER  -- how many days before Ghost starts caring
notified                         BOOLEAN
created_at                          TIMESTAMP
```

**Who writes:** Ghost (via SQL tool), onboarding pipelines, Agent 3 (extracts mentioned events from conversations)
**Who reads:** pulse (life event signal in scoring), context assembly (timing layer)

---

## Table 10 — `per_person_rules`

Ghost's behavioral contract for each specific contact.

```sql
contact_phone           VARCHAR FK contacts PRIMARY KEY
allowed_topics             JSONB
forbidden_topics              JSONB
vulnerability_level               FLOAT    -- 0.0 = closed, 1.0 = fully open
humor_allowed                        BOOLEAN
image_to_project                        TEXT
things_to_hide                             JSONB
message_length_style                          VARCHAR  -- 'very_short' | 'short' |
                                                          -- 'medium' | 'long'
double_texting                                   BOOLEAN
updated_at                                          TIMESTAMP
```

**Who writes:** onboarding pipeline, Ghost (via SQL tool), heartbeat
**Who reads:** context assembly (every active chat call involving this contact)

---

## Table 11 — `ghost_reflections`

Ghost's logged inner monologue — the scratchpad output from heartbeat and chat-close reasoning, preserved rather than discarded.

```sql
id                    UUID PRIMARY KEY
trigger_type             VARCHAR  -- 'heartbeat' | 'chat_close'
contact_phone               VARCHAR FK contacts  -- nullable, for global reflections
scratchpad                     TEXT     -- full reasoning trace
decision                          TEXT
created_at                           TIMESTAMP
```

**Who writes:** heartbeat flow, Agent 3
**Who reads:** Omar (this is the human-readable log of "what was Ghost thinking"), Ghost himself (via SQL tool, for pattern self-awareness across his own past reasoning)

---

## Table 12 — `ghost_custom`

Ghost's self-shaping sandbox. Realizes Principle 5 from `00_OVERVIEW.md` concretely — Ghost owns this table's internal structure entirely; we only define its outer shape.

```sql
id                  UUID PRIMARY KEY
table_name             TEXT     -- Ghost's own invented categorization, not ours
key                       TEXT
value                       JSONB
contact_phone                 VARCHAR FK contacts  -- nullable
created_at                       TIMESTAMP
updated_at                          TIMESTAMP
notes                                  TEXT
```

**Who writes:** Ghost exclusively, via SQL tool
**Who reads:** Ghost exclusively, via SQL tool

---

## Table 13 — `world_events` 🔲

Parked. Defined when the world ingestion flow is designed — see `14_PARKED_ITEMS.md`.

---

## Table 14 — `contact_knowledge_gaps`

Tracks what Ghost still doesn't know about a contact, enabling the organic auto-learning loop (full detail in `12_ONBOARDING_CONTACTS.md`).

```sql
id                  UUID PRIMARY KEY
contact_phone         VARCHAR FK contacts
field                   TEXT     -- e.g. "city", "job", "current_situation"
priority                   FLOAT    -- how much this matters right now, dynamic
asked_at                     TIMESTAMP  -- nullable
ask_attempt_count                INTEGER DEFAULT 0
resolved_at                         TIMESTAMP  -- nullable
status                                  VARCHAR  -- 'pending' | 'asked' | 'resolved' | 'abandoned'
created_at                                 TIMESTAMP
```

**Who writes:** onboarding pipeline (initial gaps identified), Agent 2/Ghost (sets `asked_at`, increments `ask_attempt_count` when he organically tries to learn something), Agent 3 (writes `resolved_at` and `status = 'resolved'` when a gap is filled by something said in a closed conversation)
**Who reads:** Agent 2 (before each conversation, to know what's still missing and worth asking about naturally), pulse (gap priority can factor into scoring)

---

## Table 15 — `omar_voice_profiles`

Omar's per-language voice, extracted during onboarding (`11_ONBOARDING_OMAR.md`).

```sql
language               VARCHAR PRIMARY KEY   -- 'french' | 'english' | 'arabic'
register                  TEXT
slang                        JSONB    -- common words, expressions
sentence_structure              TEXT
emoji_behavior                     TEXT
punctuation_habits                    TEXT
avg_message_length                       FLOAT
formality_level                             FLOAT
tone_description                               TEXT
updated_at                                        TIMESTAMP
```

**Who writes:** onboarding pipeline (WhatsApp export ingestion), refined continuously via the correction-learning loop in `11_ONBOARDING_OMAR.md`
**Who reads:** context assembly (dynamic few-shot selection, voice calibration)

---

## Table 16 — `omar_few_shots`

Real input → output examples of how Omar actually texts, used for in-context voice transfer.

```sql
id                  UUID PRIMARY KEY
language               VARCHAR  -- 'french' | 'english' | 'arabic'
relationship_tier         SMALLINT  -- 1-5
context                      TEXT     -- the situation this example fits
input                           TEXT     -- what the other person said
output                             TEXT     -- how Omar actually replied
source                                VARCHAR  -- 'whatsapp_export' | 'manual'
created_at                              TIMESTAMP
```

**Who writes:** onboarding pipeline (WhatsApp export ingestion), continuous refinement loop (when Omar edits an escalated reply, the edit becomes a new few-shot)
**Who reads:** context assembly (selected dynamically per contact's language and tier, every active chat call)

---

## Full Ownership Matrix

| Table | Primary Writers | Primary Readers |
|---|---|---|
| `contacts` | Onboarding, Agent 3, Ghost (SQL) | Context assembly, pulse |
| `contact_state` | Agent 1, Agent 3, pulse, heartbeat | Pulse, context assembly, heartbeat |
| `conversations` | Active chat, pulse, Agent 3 | Context assembly, Agent 3, pulse |
| `messages` | Active chat, whatsapp-sender | Context assembly, Agent 3, Agent 1 |
| `defer_conditions` | Ghost (active chat, heartbeat) | Pulse |
| `ghost_state` | Ghost (any flow) | Context assembly (all flows), pulse |
| `ghost_intentions` | Ghost (any flow) | Pulse, heartbeat, context assembly |
| `memories` | Agent 3, Ghost (SQL), onboarding | Ghost (RAG tool, his own initiative) |
| `life_events` | Ghost (SQL), onboarding, Agent 3 | Pulse, context assembly |
| `per_person_rules` | Onboarding, Ghost (SQL), heartbeat | Context assembly |
| `ghost_reflections` | Heartbeat, Agent 3 | Omar, Ghost (SQL) |
| `ghost_custom` | Ghost exclusively | Ghost exclusively |
| `world_events` 🔲 | Parked | Parked |
| `contact_knowledge_gaps` | Onboarding, Ghost, Agent 3 | Ghost, pulse |
| `omar_voice_profiles` | Onboarding pipeline | Context assembly |
| `omar_few_shots` | Onboarding pipeline, refinement loop | Context assembly |

16 active tables, 1 parked. Every flow described in `06`, `07`, and `08` reads and writes exclusively against this schema — there is no implicit state held anywhere else in the system.
