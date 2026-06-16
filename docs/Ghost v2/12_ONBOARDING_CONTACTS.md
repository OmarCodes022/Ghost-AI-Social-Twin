# 12 — Onboarding: Contacts Into Ghost

## Purpose

This document defines how Ghost builds a working profile for the people he talks to — distinct from `11_ONBOARDING_OMAR.md`, which covers Ghost's own identity. Contact onboarding is intentionally lighter-weight: the goal is just enough of a starting profile that Ghost isn't operating blind, combined with a permanent mechanism for filling in whatever starts missing, organically, over time.

---

## The Three-Layer Hierarchy

This was explicitly locked as an ordered hierarchy, not three interchangeable options — each layer exists specifically to cover what the layer before it didn't reach:

> 1. **Onboarding** — best case, a profile is established before Ghost ever talks to this person at all.
> 2. **Defaults** — anything onboarding didn't cover gets a sensible, conservative default value, so Ghost never has a *missing* field, only an *unrefined* one.
> 3. **Auto-learning** — Ghost fills remaining gaps organically, through ordinary conversation, over time.

This hierarchy matters because it was an explicit correction during design: defaults and auto-learning do not *replace* onboarding — onboarding still happens first wherever possible, with defaults and auto-learning existing specifically to handle whatever onboarding leaves incomplete, not as a substitute for doing onboarding at all.

---

## Layer 1 — Onboarding

Two sources, both already covered structurally by mechanisms defined elsewhere in this document set:

### Manual entry
Omar adds a contact directly — name, tier, language, known facts, relationship goal, per-person rules, life events — through a simple interface (an evolution of v1's `admin.py` CLI pattern, extended to cover the richer v2 schema). Used for contacts Omar wants to deliberately configure before Ghost ever interacts with them.

### WhatsApp export ingestion (shared pipeline with Omar's own onboarding)
The same ingestion run described in `11_ONBOARDING_OMAR.md` Layer 2 — which processes Omar's WhatsApp exports to build his per-language voice profile — simultaneously produces a starter profile for **every contact present in those exports**, as a side effect of the same pass over the data:

- Detects each contact's language from their messages
- Estimates their texting style (length, speed, emoji rate, formality) directly from their own message history
- Extracts known facts about them mentioned anywhere in the conversation history, written to `memories`
- Estimates an initial relationship tier from interaction frequency and tone
- Identifies any dates or events mentioned in the conversation, written to `life_events`
- Flags everything the export could *not* determine, written to `contact_knowledge_gaps`

One ingestion run, two outputs: Omar's voice profile and every known contact's starter profile.

---

## Layer 2 — Defaults

Whatever onboarding (either source) does not establish gets a sensible, conservative default, so Ghost is never operating on a genuinely empty field:

| Field | Default |
|---|---|
| `relationship_tier` | 3 (neutral, unknown) |
| `language_primary` | Detected from the contact's first message by Agent 1, if not already known |
| `trust_level` | 0.5 (neutral) |
| `risk_level` | 0.5 (neutral) |
| `vulnerability_level` (in `per_person_rules`) | 0.0 — closed by default, until trust is established |
| `texting_style` | Derived from the first few real exchanges by Agent 3, if not already known |
| `baseline_frequency` | Computed once enough interactions exist to establish a pattern |

The guiding intent: Ghost starts conservative wherever something is genuinely unknown, and calibrates upward in openness, familiarity, or specificity only as real evidence accumulates — never the reverse.

---

## Layer 3 — Auto-Learning

This is the most distinctive piece of contact onboarding in v2, and it was explicitly proposed as an improvement over a formal onboarding-only approach: rather than requiring every contact to be fully profiled up front, **Ghost learns the rest the way a real person does — through ordinary conversation, not a survey.**

### The mechanism

Backed by the `contact_knowledge_gaps` table (full schema in `09_DB_SCHEMA.md`):

1. **Gaps are recorded** — whenever something about a contact is unknown (from the export ingestion's own gaps, from a default that was never refined, or from something that simply never came up), a row exists in `contact_knowledge_gaps` with a `field` name and a `priority`.
2. **Agent 2 reads gaps before conversing** — as part of the contact's profile in context assembly, Ghost sees what's currently missing for this person.
3. **Ghost asks organically, only when it fits** — never as a questionnaire, never out of context. A natural example given directly during design: not knowing someone's location prompts something like *"où t'es maintenant?"*, asked when it naturally fits the conversation — never a direct, out-of-place request like "please provide your location."
4. **Ghost tracks his own attempts** — `asked_at` and `ask_attempt_count` ensure Ghost never repeats the same question. If he asked about someone's job last week and got no clear answer, he waits before trying again rather than asking again immediately.
5. **Agent 3 resolves gaps after the conversation closes** — reading the full closed conversation, Agent 3 checks whether any pending gap was filled, naturally, by something the contact said — regardless of whether Ghost explicitly asked or the information simply came up on its own. If filled, the contact's profile (`contacts`, `contact_state`, or `per_person_rules` as appropriate) is updated, and the gap is marked `resolved`.
6. **Priority is dynamic, not fixed** — some gaps matter more depending on context. Not knowing a contact's timezone matters far more when Ghost is deciding whether nighttime outreach is appropriate (see `10_GUARDRAILS_AND_TIMING.md`) than it does in most other moments. Priority can be adjusted by pulse or Agent 3 as relevance shifts.

### Ghost can also write to his own tables mid-conversation

If Ghost learns something worth storing *immediately*, during an active chat call, he is not required to wait for Agent 3's post-close pass — he can write directly via the SQL tool in the same call (see `03_MEMORY_SYSTEM.md`). Agent 3's post-close pass exists as the **reliable, systematic** resolution mechanism; Ghost's own in-the-moment writes are a faster, optional supplement, not a replacement for it.

---

## Full Lifecycle

```
WhatsApp export ingestion
  ├──► contacts (starter profile: tier estimate, language, texting style)
  ├──► contact_state (baseline frequency, attitude baseline from history)
  ├──► memories (facts, topics, emotional moments extracted from history)
  ├──► life_events (any dates/events mentioned)
  ├──► per_person_rules (conservative starting defaults)
  └──► contact_knowledge_gaps (everything the export couldn't determine)
        │
        ▼
Manual enrichment (Omar adds/corrects anything the export missed)
        │
        ▼
Defaults (fill anything still genuinely unset)
        │
        ▼
[Ghost begins talking to this contact — first contact or ongoing]
        │
        ▼
Auto-learning loop:
   Agent 2 reads gaps ──► asks organically when it fits ──► tracks attempts
        │
        ▼
   Agent 3 resolves gaps after each chat close ──► updates profile,
   marks gap resolved
        │
        ▼
   (loop continues indefinitely — a contact's profile is never
    considered "finished," only ever more complete)
```

A contact with zero prior history — someone messaging Ghost for the very first time with no export data and no manual entry — simply enters this lifecycle starting from Layer 2 (defaults) directly: Agent 1 detects their language from message one, every other field takes its default, every unknown field becomes a row in `contact_knowledge_gaps`, and Ghost starts learning from that very first conversation onward.
