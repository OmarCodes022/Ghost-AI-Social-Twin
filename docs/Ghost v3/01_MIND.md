# 01: Mind

Status: in progress. Covers so far: how Ghost decides to act (D-015, D-016, D-018) and feelings (D-017).
Still to come: sleep, forgetting, parallel chats, tier map, persona vs override, memory audience rules.

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
