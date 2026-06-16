# 03 — Memory System

## Purpose

This document covers how Ghost actually retrieves memory he doesn't already have pre-loaded — the Tier 2 layer described in `02_DELIVERY_MAP.md`. It preserves the reasoning behind a key architectural decision, not just the conclusion, because the reasoning explains *when* to use which tool.

---

## The Problem With v1's Memory

V1 used RAG exclusively, via Titan or Voyage embeddings over `knowledge_chunks.embedding`, a `vector(1536)` column. Two compounding failures:

1. **Dimension mismatch.** Voyage embeddings are 1024-dimensional; Titan is 1536-dimensional. The column was fixed at 1536. If Voyage was used, storage failed outright (pgvector rejects wrong dimensions). If somehow stored, cosine distance between differently-dimensioned vectors is mathematically undefined.
2. **Language bias.** With Titan throttled and no Voyage key configured, zero embeddings were being created at all. RAG silently fell back to unfiltered identity chunks on every single call — meaning the "memory system" was a slow no-op wearing a working appearance. Even when embeddings did exist, Titan is English-biased, so French and Arabic queries searched poorly against it.

The lesson carried into v2: **embeddings must be dimension-consistent end-to-end, and the embedding model must be genuinely multilingual from the start** — Omar speaks French, English, and Arabic fluently, and Ghost's memory has to work identically well across all three.

---

## The Debate: Replace RAG With Ghost-Driven SQL?

A serious proposal was raised: instead of RAG, give Ghost the database schema directly and let him write his own SQL queries — full agency, no vector search, no embedding dimension problems, no multilingual fragility.

This was evaluated honestly rather than accepted or dismissed outright.

### What's genuinely good about SQL-driven retrieval

- **No embedding problems at all.** The multilingual RAG issue disappears completely, because retrieval becomes logic-based rather than semantic-similarity-based.
- **Real agency.** Ghost decides what to look for, rather than a vector search algorithm deciding what's "similar enough." More aligned with the autonomy principle.
- **More precise for structured data.** Facts, dates, relationship history — these are better served by an exact query ("give me this person's birthday") than by cosine similarity, which is overkill for lookups that have an exact answer.
- **No cold-start problem.** RAG degrades badly when the dataset is small, because there isn't enough data for embeddings to be meaningful. SQL works correctly even with a single row.

### The real challenges with SQL-only retrieval

- **Latency.** Every SQL lookup is a tool call — call, wait, read, decide if more is needed, call again. A single RAG injection arrives pre-assembled in one shot; SQL-only retrieval can mean 3-4 round trips before Ghost has what he needs.
- **Token cost.** Multiple round trips cost more tokens cumulatively than one well-executed retrieval.
- **Ghost doesn't know what he doesn't know.** This is the most important failure mode. RAG can surface something relevant that Ghost didn't think to ask for — semantic similarity surprises you in useful ways. If Ghost only writes SQL, he only ever retrieves what he already knew to query for. A perfectly relevant memory that he simply didn't think to look up is permanently invisible to him under SQL-only retrieval.
- **Schema exposure and stability.** Ghost needs the schema to query it, so the schema has to stay clean and stable, or his queries break.
- **Hallucinated SQL.** LLMs sometimes produce syntactically invalid queries, especially with joins or edge cases, requiring a safe execution layer with error feedback and retry.

### The resolution

These two approaches solve *different* problems and are not mutually exclusive:

- **SQL** → structured, precise, logic-based retrieval. Best for facts, profiles, events, relationship metadata, Ghost's own notes — anything with an exact, queryable answer.
- **RAG** → semantic, fuzzy, language-agnostic retrieval. Best for episodic memories, conversation summaries, and anything Ghost didn't know to explicitly look for.

**Decision: Ghost gets both tools.** He decides which to use based on what he's looking for. The multilingual problem that originally motivated abandoning RAG is solved at the embedding-model level instead (see below) — it was never actually a flaw in the concept of RAG, only in the specific embedding model v1 used.

---

## Embedding Model

**Voyage-3, multilingual.** Chosen specifically because it embeds French, Arabic, and English into the same vector space — a query in any of the three languages can retrieve semantically similar memories regardless of what language they were originally stored in. This directly fixes the v1 bug where Ghost always searched in English regardless of the conversation's actual language.

The `memories` table embedding column is fixed at `vector(1024)` to match Voyage-3's output dimensionality, end to end, with no mixed-dimension fallback path. There is exactly one embedding model in v2. No dual-path Titan/Voyage logic exists, removing the entire class of bug that broke v1's RAG.

---

## What Ghost Retrieves Himself (Tier 2)

From `02_DELIVERY_MAP.md`, the categories Ghost fetches on his own initiative:

| Need | Tool |
|---|---|
| Deep episodic memories about a person | RAG |
| Specific known fact (birthday, job, city) | SQL |
| Relationship history (full arc) | SQL or RAG, Ghost's choice depending on whether he needs an exact fact or a fuzzy sense of the pattern |
| Cross-contact awareness | SQL |
| Deep persona content (life story, interests) | RAG |

RAG is never run as an automatic pre-call injection in v2 (unlike an earlier draft of this architecture). Ghost decides when he needs it and calls it himself — this preserves his agency over his own memory and avoids injecting irrelevant context on every call regardless of whether it's needed.

---

## Ghost's Self-Shaping Memory — `ghost_custom`

Beyond retrieving what already exists, Ghost needs the ability to **write his own memory in his own structure**, not just the fixed tables predefined by this architecture. This satisfies Principle 5 from `00_OVERVIEW.md`.

The `ghost_custom` table (full schema in `09_DB_SCHEMA.md`) is a flexible key-value-style sandbox that Ghost owns exclusively:

- Ghost decides the categorization (`table_name` field is Ghost's own invented taxonomy, not ours)
- Ghost decides what's worth storing that doesn't fit any of the predefined tables
- Ghost reads and writes to it via the same SQL tool used for structured queries elsewhere
- We do not predefine its internal schema beyond key/value/notes — Ghost shapes it as he goes

This is the concrete mechanism behind the abstract requirement that "Ghost must have the tools to shape his own DB the way he likes."

---

## Summary

- Two retrieval tools: **SQL** (precise, logic-based) and **RAG** (semantic, multilingual via Voyage-3)
- Ghost chooses which to use, based on the nature of what he's looking for
- No automatic pre-call RAG injection — retrieval is always Ghost's own initiative
- One embedding model, one fixed dimensionality, no mixed-path fallback — this is what actually fixes the v1 bug
- `ghost_custom` gives Ghost a genuine sandbox for self-authored memory structure, separate from anything we predefined
