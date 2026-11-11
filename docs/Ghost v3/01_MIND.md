# 01: Mind

Status: in progress. Covers so far: acting (D-015, D-016, D-018), feelings (D-017), sleep (D-019), fading (D-020), parallel chats (D-021), tier map (D-022).
Still to come: persona vs override, memory audience rules, tools, one agent vs many.

## The four parts

| Part | Job |
|------|-----|
| **Senses** | Things come in |
| **Memory** | Stores facts, people, summaries. Passive. |
| **Signals** | Short list of "things on his mind", each with a reason and a strength |
| **Pulse + Heartbeat** | Pulse reads signals cheaply every tick; Heartbeat thinks and acts |

The expensive part, understanding something, happens **once, at intake**. Pulse never scans the DB or the chats. Cost grows with what happens, not with time x contacts.

## Flow

```
Senses ──> intake step ──> memory
                      ├──> signals
                      └──> feeling changes

Pulse (every tick, reflex): drift feelings, fade signals, check thresholds
   └──> instinct: "now?" (confidence)
          └──> Heartbeat (thought): gets the signal's reason + top feelings
                 └──> act / update memory / ignore / write new signals
```

A strong signal (an incoming message) wakes Pulse at once instead of waiting for the next tick.

## Senses (open-ended)

- Live messages and ended-chat summaries
- Posts, stories, news
- Silence: left on read, a streak broken, someone stopped replying
- Presence: online, typing, status or profile picture changed
- Real world: birthdays, holidays, their time of day, weather, big events
- The owner's manual messages
- Random recall: Pulse sometimes surfaces an old memory (nostalgia)
- Other Ghosts, group chats
- Time passing, his own feelings

## Signals (open-ended)

| Kind | Example |
|------|---------|
| reply-owed | someone texted, he hasn't answered |
| tell | Sara's news for Ahmed |
| check-in | drifting from Youssef |
| follow-up | "how was the exam?" |
| share | a post that made him think of someone |
| mood | bored, wants someone fun |
| unfinished | an argument, a question left hanging |
| goal | get closer to X |
| celebrate / comfort / repair / reciprocate / plan / flirt / react | |

Written by: the intake step, feelings past a threshold, and Ghost himself while thinking.
Signals grow, fade, die, and can come back stronger. He can act on several in the same minute.

## Nothing is a hard block

Time of day, how the last chat ended, them being busy, double texting, his own tiredness, sensitive info, their timezone: all of these **lower the odds**, never forbid. The only hard stop is owner takeover (D-008), which is control, not judgment.

## Feelings

**Core affect** (always present, cheap for Pulse): mood (good to bad), energy (tired to hyper), social battery.

**Named feelings** (unlimited, Ghost can invent new ones):

| Field | Example |
|-------|---------|
| name | annoyed |
| intensity | 0.7 |
| target | Sara (optional) |
| cause | "she cancelled", message at 14:02 |
| baseline | where it drifts back to |

**What changes them**
- Senses: the intake step writes feeling changes alongside signals.
- Time: Pulse drifts them each tick. Most fade to baseline; some grow (boredom while idle, missing someone).
- Personality: baselines and rates belong to the Ghost; he retunes them during sleep.

**What they change**
1. Outreach: a feeling past its threshold writes a signal.
2. Odds: instinct weighs them (annoyed at Sara, slower to reply to her).
3. Tone and subject: Heartbeat gets the top feelings with their causes. No templates.

**Spillover:** a targeted feeling bleeds a little into core affect, so annoyance at Sara shortens a reply to Ahmed.

## Why not v2's pulse formula

v2 had the right skeleton but `functions/pulse/scoring.py`:
- scored per contact only, so boredom could never trigger anything;
- buried hot news: one intention added 0.05 against a 0.65 threshold;
- hardcoded the judgment in `WEIGHTS` and fixed good hours;
- woke the heartbeat with only `"threshold_crossed"`, so Sonnet started blind.

## Sleep

- Ghost decides when he sleeps, from his energy. No fixed bedtime.
- The owner can put him to sleep or wake him from the app.
- Asleep, he doesn't reply. Nothing wakes him (for now). Messages wait.
- On waking he gets through the backlog slowly, not all at once.
- No naps.
- **Dreaming** is one batched pass during sleep: consolidate memory, find links the intake step missed and write signals for tomorrow, retune baselines and rates, reset core affect.

## Fading (not forgetting)

RAG already keeps the context window small, so fading is not about space. It is about **relevance**:

1. **Ranking.** Over years, old and outdated memories compete with fresh ones in search ("Ahmed's girlfriend" should return the current one). Strength is part of the ranking.
2. **What surfaces on its own.** Random recall, outreach ideas and nostalgia pick from strong memories, so he doesn't bring up a 3-year-old detail out of nowhere unless it mattered.
3. **Focus.** Strength keeps the heartbeat's context on what matters now.

In a chat, a direct cue ("remember the trip?") still finds a faded memory, because fading changes rank, not existence.

- Memories have a strength: it fades slowly (he forgets less than a human), recall and mentions raise it, emotional and important memories fade slower.
- Outdated facts are **superseded** in dreams (Sara moved: the old city becomes history), not deleted.
- Locked memories never fade.
- No misremembering.
- Only the owner can truly delete a memory, manually.

## Parallel chats

- Several heartbeats run at once, one per contact, on the same live state (one mind, D-006).
- One heartbeat per contact at a time.
- **Bursts are one turn.** Messages from the same person are grouped and answered together. The answer can be one message or several; Ghost decides. When a burst is "done" is an instinct call (typing indicator, gaps), detailed in Body (session 3).

## Tier map

Each decision starts at the lowest tier that can make it; low confidence escalates.

| Decision | Tier |
|----------|------|
| Drift feelings, fade signals, check thresholds | Reflex |
| Owner takeover? Contact assigned? | Reflex |
| Intake: is this worth a signal, feeling change or memory? | Instinct (dreams catch misses) |
| Act on a signal now, later, or drop it | Instinct |
| Is this burst done? | Instinct |
| Who to text when bored (shortlist) | Instinct |
| Ghost-to-Ghost loop? | Instinct |
| React only, or write? | Instinct |
| Write the message, pick media | Thought |
| Final pick of who and what when bored | Thought |
| Dreaming | Thought (batched) |
| Change his own baselines, invent a feeling | Thought |
