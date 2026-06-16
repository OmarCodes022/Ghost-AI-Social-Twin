# 11 — Onboarding: Omar Into Ghost

## Purpose

This document defines how Omar's actual identity gets into Ghost — not a summary of Omar, but Omar himself, as completely as the architecture can transfer. This is the deepest and most consequential onboarding pipeline in the system: without it, every other piece of this architecture has nothing to actually express.

This pipeline produces the content for category 1 ("Who Ghost Is") from `01_INFORMATION_ARCHITECTURE.md`, delivered per the gateways assigned in `02_DELIVERY_MAP.md`, and populates three specific tables defined in `09_DB_SCHEMA.md`: `memories` (category `'identity'` and `'behavioral'`), `omar_voice_profiles`, and `omar_few_shots`.

---

## Why This Needs Multiple Sources

When asked how Omar should get into Ghost, the answer given was deliberately not singular: "either, a combination of all probably." This is the correct answer because no single source can produce everything needed:

- A structured interview is good at extracting reflective, narrative content (life story, values, opinions) but cannot capture *how* Omar actually writes in the moment.
- Real WhatsApp history is good at capturing authentic voice and patterns but contains no explicit reflection on *why* Omar is the way he is.
- Neither source alone produces ongoing correction — both are point-in-time snapshots unless something keeps refining them.

The pipeline therefore has four layers, each covering what the others cannot.

---

## Layer 1 — Structured Interview

A dedicated, deep conversation — not a form, not a quick questionnaire — covering everything in category 1 of `01_INFORMATION_ARCHITECTURE.md`: full life story, values, deep interests with actual opinions and nuance (not just topics), humor style, social behavior patterns, emotional defaults, what Omar never brings up, the people and experiences that shaped him, his current life situation in depth, global image management, and his rules and limits.

This is explicitly **not** something that can be compressed into a short form — the volume of content here (a full life story alone) was specifically why this couldn't simply be folded into a "who is Ghost" subsection in the system prompt; it has to be processed and stored as retrievable content (`memories`, category `'identity'`), not crammed into the system prompt directly.

**Process:** a dedicated interview session (can be run as its own focused conversation, separate from general Ghost architecture discussions) where every category-1 item is covered conversationally, not as a checklist. The output is extracted, structured, and written to `memories` with `contact_phone = NULL` and `category = 'identity'`, embedded via Voyage-3 for later RAG retrieval by Ghost.

---

## Layer 2 — Voice Extraction From WhatsApp Exports

Omar's real WhatsApp history — ideally spanning many different contacts and contexts — is fed into a dedicated ingestion pipeline. This is distinct from, but built on the same base mechanics as, v1's `ingest_whatsapp.py` (which already correctly handled iOS/Android export formats, multi-line continuation, and session chunking). In v2 this script is extended to produce richer, per-language output rather than a single undifferentiated voice profile.

**What the pipeline extracts, specifically:**

1. Identifies which messages are Omar's vs. the other party's
2. Detects the language of each of Omar's messages individually
3. Groups Omar's messages by language
4. Analyzes voice patterns **independently per language** — register, slang, sentence structure, emoji behavior, punctuation habits, average message length, formality level, overall tone — because, as established directly during design, these do not transfer between languages; French Omar, English Omar, and Arabic Omar are voice-distinct
5. Extracts real input→output examples as few-shots, each tagged by the language it occurred in, the relationship tier of the contact involved, and a short description of the context the example fits
6. Writes the per-language analysis to `omar_voice_profiles` (one row per language)
7. Writes the extracted examples to `omar_few_shots`

**As a side effect**, this same ingestion run also extracts starter contact profiles for everyone present in the exports — this is covered in `12_ONBOARDING_CONTACTS.md` rather than here, but it is the same physical pipeline run, producing two different categories of output simultaneously.

---

## Layer 3 — Omar Writes Directly

Some content can only come from Omar writing it himself, with no interview structure imposed — particularly genuine opinions and stances, the specific things that shaped him, the people who matter, and what he deliberately never discusses. This is a freeform document, written at Omar's own pace and in his own structure, which then gets ingested: read, parsed, categorized against the relevant slice of category 1, and written into `memories` exactly as Layer 1's output is.

This layer exists specifically because a structured interview format can subtly shape or flatten what someone says — some things come out more honestly when written without a question prompting them.

---

## Layer 4 — Continuous Refinement

Onboarding is never actually finished; it is a starting point. The mechanism that keeps it alive:

- Every time Omar **edits an escalated message** rather than sending it as Ghost wrote it (via the Telegram Send/Edit/Skip flow, carried forward from v1), the edit is compared against what Ghost originally produced.
- The delta between the two is analyzed: what changed, and does it reveal a pattern (a phrase Omar would never use, a tone correction, a length preference)?
- If the delta represents a clean example, it is written directly into `omar_few_shots`, tagged with the language and context it occurred in, exactly as if it had come from the original WhatsApp export ingestion.
- If a pattern recurs across multiple corrections (e.g., Omar consistently shortening Ghost's replies in a specific language), `omar_voice_profiles` for that language is updated to reflect it.

This means every correction Omar makes makes Ghost better at being Omar going forward — the v1 roadmap item "override learning loop" (originally scoped narrowly as saving an edit as a `behavioral` knowledge chunk) is generalized here into the full continuous refinement mechanism across both voice profiles and few-shots, not just a single memory category.

---

## Where Everything Lands

| Source | Destination table(s) | Category/tag |
|---|---|---|
| Structured interview | `memories` | `category = 'identity'`, `contact_phone = NULL` |
| WhatsApp export — voice analysis | `omar_voice_profiles` | one row per language |
| WhatsApp export — real examples | `omar_few_shots` | tagged by language, tier, context |
| WhatsApp export — social patterns | `memories` | `category = 'behavioral'` |
| Omar's freeform writing | `memories` | `category = 'identity'`, parsed and categorized on ingestion |
| Escalation edit corrections | `omar_few_shots` (always) + `omar_voice_profiles` (if a pattern emerges) | ongoing |

---

## Pipeline Order

```
Layer 1: Structured interview
        │  (life story, values, opinions, social patterns, rules)
        ▼
Layer 2: WhatsApp export ingestion
        │  (per-language voice profiles + few-shots + contact starter profiles)
        ▼
Layer 3: Omar's freeform writing
        │  (opinions, stances, what shaped him, what he hides)
        ▼
[Ghost is now live and operating]
        │
        ▼
Layer 4: Continuous refinement
         (every escalation edit feeds back into omar_few_shots
          and, when patterns emerge, omar_voice_profiles)
```

Layers 1 through 3 can happen in any order or in parallel — they are independent content sources. Layer 4 is permanent and ongoing from the moment Ghost goes live, with no defined endpoint.
