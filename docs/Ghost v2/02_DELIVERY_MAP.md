# 02 — Delivery Map

## Purpose

This document defines *how* each of the 10 information categories from `01_INFORMATION_ARCHITECTURE.md` actually reaches the model. It is built on a reduction: there are only 5 true gateways into an LLM. Everything else — few-shot examples, RAG, summarization, structured data, chain-of-thought — is a *strategy* for populating one of those 5 gateways, not a separate channel.

---

## The 5 Primitives

| Primitive | Nature | Best for |
|---|---|---|
| **System Prompt** | Static, pre-conversation, highest authority | Identity, rules, stable background knowledge |
| **Human Turn** | Live, per-request input | Anything dynamic and per-request — text, documents, retrieved chunks, current state |
| **Assistant Turn** | Prior model outputs, real or fabricated | Behavioral continuity, self-consistency across turns, chain-of-thought seeding |
| **Tool Results** | Structured data returned mid-conversation | Dynamic, on-demand context fetched from DBs, APIs, vector stores |
| **Fine-Tuning** | Pre-inference, bakes knowledge into weights | Foundational knowledge that never changes; bypasses the context window entirely |

### The 15 methods, mapped to their gateway

These are not additional primitives — they are *how* you populate one of the 5 above.

| Method | Gateway |
|---|---|
| Few-shot examples | System prompt or human turn |
| RAG | Tool result |
| Conversation history | Assistant + human turns |
| Structured data (JSON, tables) | Human turn or tool result |
| Chain-of-thought seeding | Assistant turn |
| File injection | Human turn (multimodal content block) |
| Scratchpad | Assistant turn |
| Long-term memory | Tool result (fetched from DB) |
| Summarization | Human turn (compressed history injected) |
| Agent-to-agent output | Human turn or tool result |
| Prompt caching | Not new context — a cost/latency optimization layered on system prompt and other static content |

### The decision rule

For any given piece of information, ask, in order:

1. **Is it always needed, small, and stable?** → System prompt
2. **Does it change per request, and is it dynamic?** → Human turn
3. **Is it too big to always include?** → Tool result (RAG)
4. **Does it need to persist across sessions and be queried precisely?** → Tool result (external memory DB, via SQL)
5. **Is it foundational and never changes?** → Fine-tuning (not used in v2 — see below)
6. **Does it need to control behavioral continuity across turns?** → Assistant turn

---

## Why Fine-Tuning Is Not Used (Yet)

Fine-tuning bakes knowledge into model weights, removing prompt overhead for stable knowledge. It is explicitly the wrong starting point for Ghost v2: it is expensive, slow to iterate on, and you lose the benefit every time the base model updates. Fine-tuning is the **endgame**, applicable only once Ghost's voice and behavior are already correct and stable in prompt form, as an optimization — not as part of the initial build. Every category in this document is therefore routed through one of the other 4 primitives.

---

## Category-by-Category Assignment

### 1. Who Ghost Is

This category splits across three gateways because it is too large and has parts of differing stability:

- **Core identity, values, rules, limits, image management (global)** → **System Prompt**, compressed and dense, cached. This is what must always be present and never changes per-request.
- **Full life story, deep interests, per-language voice (the deep version)** → **Tool Result via RAG.** Too large to always include in full; retrieved based on relevance to the current contact and moment.
- **Few-shot voice examples per language** → **Human Turn**, dynamically selected based on the current contact's language and relationship tier.

### 2. Ghost's Inner State

Changes continuously, always needed, small in size → **Human Turn**, pulled fresh from `ghost_state` and serialized into the prompt on every call.

### 3. The World Right Now

Changes continuously, always needed, small in size for most of it → **Human Turn**, assembled fresh every call (time, date, calendar). The news/world-event component, when it exists, is **Tool Result** — fetched only when relevant, not always included (see `14_PARKED_ITEMS.md`).

### 4. Who He's Talking To

Per-contact, changes slowly, medium size, always needed during any interaction with that contact → **Human Turn**, serialized from the `contacts` and `contact_state` tables and injected every call involving this contact.

### 5. Per-Person Rules

Per-contact, changes slowly, small, always needed in any active conversation with that contact → **Human Turn**, serialized from `per_person_rules` and injected every call.

### 6. What Ghost Remembers About This Person

Grows unboundedly, only a fraction is relevant at any moment → **Tool Result via RAG** (multilingual embeddings — see `03_MEMORY_SYSTEM.md`). Ghost's own freeform notes live in the same retrieval layer.

### 7. The Conversation Itself

- **Recent message window** → **Human Turn + Assistant Turn** — the actual back-and-forth, injected as real conversation turns
- **Older history** → **Human Turn**, as a compressed summary, never as raw messages
- **Conversation quality, tone, unresolved threads, patterns** → **Human Turn**, as derived metadata serialized from `conversations`

### 8. Relationship History

- **Short compressed summary of the relationship arc** → **Human Turn**, always injected
- **Full evolution, peaks/dips, what breaks silence** → **Tool Result via RAG**, retrieved on demand — particularly relevant during heartbeat reflection

### 9. Cross-Contact Awareness

Potentially large, only relevant occasionally → **Tool Result via RAG**, retrieved only when a name or mutual connection surfaces in the current context.

### 10. Timing & Life Events

Small, always relevant when present, per-contact → **Human Turn**, pulled from `life_events` and injected as part of the contact context package.

---

## Summary Table

| Category | Primary Gateway | Method |
|---|---|---|
| Who Ghost Is (core) | System Prompt | Compressed identity, cached |
| Who Ghost Is (deep) | Tool Result | RAG |
| Who Ghost Is (voice) | Human Turn | Dynamic few-shots |
| Ghost's Inner State | Human Turn | Serialized DB pull |
| The World Right Now | Human Turn (+Tool Result for news) | Fresh assembly |
| Who He's Talking To | Human Turn | Serialized DB pull |
| Per-Person Rules | Human Turn | Serialized DB pull |
| What Ghost Remembers | Tool Result | Multilingual RAG |
| The Conversation | Human + Assistant Turn | Rolling window + summary |
| Relationship History | Human Turn + Tool Result | Summary always, RAG on demand |
| Cross-Contact Awareness | Tool Result | RAG on demand |
| Timing & Life Events | Human Turn | Serialized DB pull |

---

## The Two-Tier Principle This Produces

Across every category, the same pattern emerges, and it becomes the architectural backbone of context assembly (detailed per call type in `06_ACTIVE_CHAT_FLOW.md`, `07_PULSE_FLOW.md`, `08_HEARTBEAT_FLOW.md`):

**Tier 1 — Pre-assembled, automatic.** Everything that is always needed, structured, and not too large gets built into the human turn before Ghost ever starts reasoning. No tool call, no decision required, no latency cost. This covers identity essentials, inner state, world context, contact profile, per-person rules, conversation history, and timing.

**Tier 2 — Ghost-driven, on demand.** Everything large, unbounded, or genuinely uncertain in relevance is left for Ghost to retrieve himself, using either the RAG tool or the SQL tool, based on his own judgment of what he needs (see `03_MEMORY_SYSTEM.md` for the full reasoning behind giving Ghost both tools rather than one).

This split exists specifically to satisfy **Principle 3** from `00_OVERVIEW.md`: memory must be available, not fetched — but only for the things that are always relevant. Anything else is something Ghost actively chooses to go get, preserving his agency over his own memory.
