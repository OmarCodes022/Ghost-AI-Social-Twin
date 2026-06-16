# 15 — Build Roadmap

## Purpose

This document proposes a build order across everything specified in documents 00–14, based purely on dependency — what has to exist before something else can be meaningfully built or tested. It is a suggestion, not a constraint; nothing in the architecture itself requires this exact sequence.

---

## Dependency Logic

A few structural facts drive the ordering:

- The **database schema** (`09`) underlies every flow — nothing can be meaningfully built against a flow document without the tables it reads and writes existing first.
- **Agent 1 (Perception)** has no dependency on Ghost's identity at all — it can be built and tested in isolation before any onboarding has happened.
- **Agent 2 (Ghost)** cannot produce anything authentic without at least a minimal version of Omar's identity (`11`) existing — even a partial Layer 1 interview is enough to start, but building Ghost's core loop against an empty identity produces nothing useful to evaluate.
- **Pulse** (`07`) depends on `contact_state`, `defer_conditions`, and `ghost_intentions` already being written to by something — meaning active chat (`06`) and at least a stub of heartbeat (`08`) should exist before pulse has anything real to read.
- **Heartbeat** (`08`) depends on pulse existing to trigger it, but its *internal* logic (context assembly, decision-making) can be built and tested with a manually-constructed trigger payload before pulse is wired up for real.
- **Contact onboarding** (`12`) depends on the WhatsApp export ingestion pipeline built for Omar's onboarding (`11`) — they are explicitly the same physical pipeline producing two outputs.
- **Infrastructure** (`13`) is not a separate phase — each piece of infrastructure should be stood up exactly when the flow that needs it is being built, not all at once up front.

---

## Suggested Phases

### Phase 0 — Foundation
- Stand up RDS + pgvector, RDS Proxy, all 16 tables from `09_DB_SCHEMA.md`
- Stand up SSM parameter structure (`13_INFRASTRUCTURE.md`) — environment-scoped from day one, never retrofitted later
- Base SAM template with IAM roles, scoped per the least-privilege model in `13`

### Phase 1 — Omar's Identity (minimum viable)
- Run Layer 1 (structured interview) from `11_ONBOARDING_OMAR.md` — at least enough to populate core `memories` (`category = 'identity'`) and a first pass at `omar_voice_profiles` / `omar_few_shots` if any WhatsApp export data is available
- Without this, nothing built in Phase 2 has anything authentic to express

### Phase 2 — Agent 1 (Perception) + Agent 2 (Ghost), response mode only
- Build Agent 1 in isolation — no Ghost identity dependency, testable immediately against raw message samples
- Build Agent 2 in response mode only (decide + respond from `06_ACTIVE_CHAT_FLOW.md`), using whatever identity content exists from Phase 1
- Build `ghost-context-assembler` for the active-chat call type specifically (Tier 1 package per `02_DELIVERY_MAP.md`)
- At this point Ghost can receive a message and produce a reasonable reply — no autonomy yet, no defer/condition system yet, just the core voice loop

### Phase 3 — Active Chat Flow, complete
- Wire up the full pipeline from `06_ACTIVE_CHAT_FLOW.md`: webhook receiver, deduplication, burst collection, the full SQS chain (`inbound-message-queue`, `perception-output-queue`, `outbound-message-queue`), `ghost-whatsapp-sender`
- Implement the condition system (`05_CONDITION_SYSTEM.md`) — defer conditions, conversation close conditions — even though nothing is evaluating them yet (that's Phase 4)
- Implement Ghost's inline internal updates (Step 6 of `06`) via the SQL tool
- At this point: Ghost can hold a real WhatsApp conversation, decide to reply or consciously defer, and update his own state — but deferred messages and closed conversations just sit there until pulse exists

### Phase 4 — Pulse
- Build `ghost-pulse` per `07_PULSE_FLOW.md`: the self-perpetuating SQS loop, global/contact state reads, condition evaluation, the continuous weighted scoring system, guardrail filters (`10_GUARDRAILS_AND_TIMING.md` — language and time only, to start)
- At this point: deferred messages and closed conversations from Phase 3 actually get picked up and acted on
- Build Agent 3 (Memory Processor) per `06_ACTIVE_CHAT_FLOW.md` Step 10 and `04_AGENT_ARCHITECTURE.md` — triggered by pulse resolving a conversation's close condition

### Phase 5 — Heartbeat
- Build Agent 2's heartbeat mode per `08_HEARTBEAT_FLOW.md` — per-contact invocation, scratchpad reasoning logged to `ghost_reflections`, the full decision set (reach out / reply to deferred / stay silent / update state / update intention / do nothing)
- Wire `heartbeat-queue` as pulse's actual output target, replacing whatever manual trigger was used to test heartbeat logic in isolation
- This is the point at which Ghost's full autonomy loop — Principle 1 and Principle 2 from `00_OVERVIEW.md` — is actually live end to end

### Phase 6 — Contact Onboarding + Auto-Learning
- Build the WhatsApp export ingestion pipeline per `12_ONBOARDING_CONTACTS.md` (shares its core with the Omar voice-extraction pipeline from Phase 1 — building them together, rather than sequentially, may be more efficient in practice even though they're presented as separate phases here)
- Implement `contact_knowledge_gaps` reads in Agent 2 and writes in Agent 3, completing the auto-learning loop
- Implement manual contact entry as a simple admin interface

### Phase 7 — Continuous Refinement
- Wire the escalation-edit-to-few-shot pipeline described in `11_ONBOARDING_OMAR.md` Layer 4 — every Telegram edit becomes a learning signal
- This phase has no real "completion" — it's permanent and ongoing from this point forward

### Phase 8 — Hardening
- Expand guardrails beyond language and time (`10_GUARDRAILS_AND_TIMING.md` notes this as an explicit placeholder)
- Tune pulse scoring weights based on observed real behavior (explicitly left as configuration, not fixed constants, per `07_PULSE_FLOW.md`)
- Set up the monitoring and alerting described in `13_INFRASTRUCTURE.md`

### Phase 9+ — Parked Items
- World ingestion (`14_PARKED_ITEMS.md`) and multi-platform expansion (`14_PARKED_ITEMS.md`), each designed in full — following the same process used for every flow in this set (define the trigger, define reads/writes, define any agent involved, lock it into the relevant documents) — before implementation begins on either.

---

## What This Roadmap Deliberately Does Not Do

It does not assign time estimates, and it does not assume any particular team size or working pace. It is a dependency-ordered checklist, not a schedule. Phases 6 and 7 in particular could reasonably be pulled earlier or run in parallel with Phases 3-5 if it's more convenient to build the onboarding pipeline before or alongside the live flows it feeds — the only hard ordering constraint is that **identity (Phase 1) precedes any meaningful evaluation of Ghost's voice (Phase 2 onward)**, and **active chat (Phase 3) precedes pulse (Phase 4) precedes heartbeat (Phase 5)**, since each is the literal trigger source for the next.
