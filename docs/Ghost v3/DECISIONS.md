# Decisions

Locked decisions, newest last. Changing one means a new entry that supersedes it.

| ID | Date | Decision | Why |
|----|------|----------|-----|
| D-001 | 2026-11-08 | Design first: no v3 code until the session docs are agreed. | v2 drifted from its docs. |
| D-002 | 2026-11-08 | A Ghost is someone (its subject), never an assistant. Control lives in the app and lab, not in chat. | Keeps identity and control cleanly separate. |
| D-003 | 2026-11-08 | Layering is Ghost + Persona + Override. | Omar talks differently to different people while staying himself. |
| D-004 | 2026-11-08 | Persona templates hold style only, never facts. Facts live in the Ghost's memory with audience rules. | Lets personas be shared across Ghosts without leaking facts. |
| D-005 | 2026-11-08 | Multiple Ghosts per app; subjects can be the owner, another real person, or fictional. Omar's Ghost is the main one. | "I am immortal. Everyone is." |
| D-006 | 2026-11-08 | One mind per Ghost across all conversations and platforms. | He links chats the way Omar would. |
| D-007 | 2026-11-08 | Ghost is always awake: reads feeds, has moods, sleeps, evolves, shapes his own memory. Locked memories cannot be rewritten by him. | Alive, not just event driven; locked core keeps him anchored. |
| D-008 | 2026-11-08 | Owner chooses which contacts Ghost takes over (or all), can reply manually any time, and Ghost resumes by reading what was said. | Owner and Ghost share the same accounts. |
| D-009 | 2026-11-08 | Platform order: WhatsApp, Instagram, Snapchat. | Omar's actual usage. |
| D-010 | 2026-11-08 | Phase one: no limits, no AI disclosure, unofficial clients allowed. | Build the imagined Ghost first, restrict later. |
| D-011 | 2026-11-08 | Aliveness runs on cheap logic; model calls only when worth it. | Budget. Carries over v2's pulse idea. |
| D-012 | 2026-11-08 | Accounts are separate from Ghosts. Per contact on an account, the owner assigns Ghost + Persona + Overrides. A dedicated number can be fully assigned to one Ghost. The app itself is a channel. | Covers both "different Ghosts on my number" and "a Ghost with his own number". |
| D-013 | 2026-11-08 | Three tiers of thinking: reflex (pure logic), instinct (fast structured decisions with confidence), thought (full model). Low confidence escalates up. | Aliveness on a small budget; replaces v2's math-only pulse with a smarter cheap middle layer. |
| D-014 | 2026-11-08 | Ghosts can talk to each other. | Nothing stops it in the real world either; a loop brake handles the failure case (Q-011). |
| D-015 | 2026-11-08 | Outreach runs on Pulse + Heartbeat (v2's skeleton) with four fixes: (1) Pulse reads **signals** (items with a reason and a strength, written at intake, by drives, or by Ghost himself), not a fixed weighted formula; (2) drives (inner stats) live in Pulse and can launch a heartbeat with no contact attached; (3) the heartbeat receives the signal's reason; (4) an instinct gate sits between Pulse and Heartbeat, and Ghost owns thresholds and rates. | v2's formula could not express boredom, buried hot news (one intention added 0.05 against a 0.65 threshold), hardcoded the judgment in weights, and woke Sonnet blind ("threshold_crossed"). Understanding happens once at intake, so cost scales with events, not time x contacts. |
| D-016 | 2026-11-11 | An incoming message is a signal (reply-owed, very strong). One queue for replies and outreach; a strong signal wakes Pulse at once instead of waiting for the next tick. | One mind, not a reply bot plus an outreach bot. Replies and outreach compete fairly, and mood applies to both. |
| D-017 | 2026-11-11 | Feelings have two layers: core affect (mood, energy, social battery) and named feelings (unlimited, Ghost can invent new ones), each with intensity, optional target, cause and baseline. Senses push them, Pulse drifts them over time, Ghost retunes baselines and rates in sleep. Feelings write signals, weigh instinct, and reach the heartbeat with their causes; targeted feelings spill into core affect. | Cheap dials for Pulse, meaning for the model, links across chats, and every reply is explainable in the lab. |
| D-018 | 2026-11-11 | Nothing in Ghost's judgment is a hard block: time of day, last chat, busy, double texting, sensitivity only lower the odds. Senses, signal kinds and signal writers are open-ended. He can text several people at once; signals fade and can come back. Owner takeover (D-008) stays a control rule, not a feeling. | Humans break their own rules; hard blocks are hardcoded judgment. |
