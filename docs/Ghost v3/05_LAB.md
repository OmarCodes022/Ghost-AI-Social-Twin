# 05: Lab

Status: done. Decisions D-059 to D-063. Omar left the lab to Claude's judgment.

The lab is the internal dashboard: see everything, explain any message, poke Ghost to test him. Not for users; they get simpler views in the product (session 6).

## Everything is an event

Every worker writes a structured event for everything it does, from day one.

| Worker | Events |
|--------|--------|
| Adapters | sensed (message, typing, read, deleted...) / acted (sent, reacted, online...) |
| Intake | memories, signals and feeling changes written |
| Pulse | each tick: drifts, fades, thresholds crossed |
| Instinct | question, answer, confidence, escalated or not |
| Heartbeat | full prompt, memories retrieved, tool calls, output, cost, time |
| Rule check | passed, or blocked and why |
| Dreamer | merged, superseded, retuned |
| Owner | pauses, takeovers, approvals, edits, nudges |

Events link into **chains**: sent message, then heartbeat, then the signal that woke it, then what created that signal.

The lab is only views on these events. If an event is saved, any view can be built later; if it isn't, nothing can recover it. That is why this is designed now (v2 could only say `threshold_crossed`).

## Views

Built first, in this order:
1. **Why?** Click any sent message and get the whole chain: what created the signal, instinct's call, the full prompt, memories used, tool calls, the rule check, why that delay. The core debugging tool.
2. **Live mind:** feelings dials, signal list with strengths, awake or asleep, active heartbeats, who he's thinking about.
3. **Stream:** every event live, filtered by contact, worker or type.

Later, on the same events:
- **Memory:** browse and search memories with source, audience, strength, locks; edit, lock, delete.
- **People:** per contact: what he knows, feelings toward them, open signals, fingerprint and override.
- **Quality:** fingerprint scores, replay, blind pick, busted rate, completeness.
- **Cost:** spend and time per worker, contact, day.
- **Data:** imports, extraction progress, what each source gave.

## Poking him

- **Inject** fake events (a message, news, a story) and watch.
- **Edit** state: feelings, signals, memories.
- **Rerun** any past heartbeat with one thing changed (memory, mood, model, prompt) and compare side by side.
- **Force** a pulse tick, sleep or wake.
- **Fast-forward time** in a sandbox to watch days of drift in minutes.
- **Sandbox contacts** that never touch a real platform.

Rerun turns "why did he say that" into "what would have changed it".

## Where it lives

A **separate internal web dashboard**, reading the same events and database. Never inside the user app: it shows raw prompts, costs and internals, and changes fast and rough while the app stays polished.

## Keeping events

Keep everything during personal testing. At scale: full detail for a recent window, then summaries. The window is set in session 7.
