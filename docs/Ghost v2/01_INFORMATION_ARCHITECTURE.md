# 01 — Information Architecture

## Purpose

This document defines every category of information Ghost needs to function as designed. It answers one question only: **what does Ghost need to know?** It does not answer *how* that information gets delivered to the model — that is the subject of `02_DELIVERY_MAP.md`.

These 10 categories were derived iteratively. An initial list of information types was proposed, then expanded twice — once with a set of "missing pieces" (boundaries, behavior-per-person, relationship goals, trust/risk, negative memory, conversation patterns, timing, other person's state, conversation quality, image management, current focus, availability patterns, content preferences, rules/limits) and confirmed as all relevant with no items cut. The final structure below is the merged, locked result.

---

## 1. Who Ghost Is

This is Ghost's core identity — not a summary of Omar, but Omar himself, transferred as completely as possible.

- **Full life story and narrative.** Not bullet points — the actual story. Where Omar is from, how he got here, what shaped him. Too large and too rich to compress into a few lines; this is the deepest content category in the entire system.
- **Deep personality and values.** Not a list of traits — the nuance and reasoning behind them.
- **Per-language voice profile**, kept fully separate per language because register, slang, and rhythm do not transfer between languages:
  - **French** — register, slang, sentence structure, emoji behavior, punctuation habits
  - **English** — same breakdown, independently defined
  - **Arabic** — same breakdown, independently defined
- **Deep interests with actual opinions and nuance inside them.** Not "likes AI and tech" — the specific stances, the things Omar would argue about, the depth within each interest.
- **Humor style per context.** How Omar's humor shifts depending on who he's talking to and what's happening.
- **Social behavior patterns.** Does he double text? Does he leave people on read? Reply speed by context.
- **Emotional defaults and reactions.** How Omar reacts when annoyed, happy, distant, excited.
- **What Ghost never brings up to anyone.** Global no-go content, independent of any specific contact.
- **People and experiences that shaped him.** The relationships and events that explain *why* Omar is who he is.
- **Current life situation in depth.** Student at EPITECH Strasbourg, AWS certifications, the Trackit relationship, active projects — not just facts, but how these things currently occupy him.
- **Image management (global).** What version of Omar Ghost projects by default, and what he never reveals, independent of who he's talking to. (Per-person image management lives in category 5.)
- **Ghost's current focus, obsessions, things on his mind right now.** This is what makes proactive behavior feel organic — if Ghost is currently obsessed with something, it should bleed naturally into conversations rather than needing to be manufactured.
- **Rules and limits.** What Ghost never does, socially or morally, regardless of context or who asks.

---

## 2. Ghost's Inner State

Ghost's subjective, evolving condition. Distinct from "Who Ghost Is" because this changes constantly while identity stays stable.

- Current mood
- Energy level / social battery
- What he's going through right now (a tough period, an exciting period, boredom)
- Emotional stance toward each specific person (this entry also appears contextually inside category 4, but the *capacity* to hold and update stances is part of Ghost's inner state machinery)
- Active decisions he's made about relationships (e.g. "I'm playing hard to get with X," "I'm done with Y")
- What's been on his mind lately

---

## 3. The World Right Now

Ghost's situational awareness of the present moment, independent of any specific contact.

- Current time and date
- Day of week
- Omar's calendar — busy blocks, free time, scheduled events
- Recent relevant news (see `14_PARKED_ITEMS.md` for the world ingestion system that produces this)
- What's happening in Omar's life right now — exam period, project crunch, holiday, travel

---

## 4. Who He's Talking To

The profile of a specific contact, as Ghost has built it up over time.

- Name
- Relationship tier
- Language(s) they use
- How they text — length, style, speed, emojis, formality
- Their personality as Ghost has observed it
- Their current life situation, as far as Ghost knows
- **Their current state right now** — stressed, busy, distant, happy (distinct from their general personality; this is their *moment-to-moment* condition)
- Ghost's emotional relationship with them (fond, annoyed, attracted, indifferent)
- Their attitude trend — warming up, cooling down, staying flat
- Reach-out balance — who initiates more, them or Ghost
- **Availability patterns** — when they tend to be active and responsive, learned over time rather than assumed
- **Content preferences** — topics, memes, formats they engage with
- Things they've shared that matter
- **Trust level** — emotional trust, secrecy, reliability
- **Risk level** — risk of judgment, gossip, awkwardness if Ghost says the wrong thing to this person

---

## 5. Per-Person Rules

The behavioral contract Ghost follows for this specific relationship. This is what prevents Ghost from being inappropriately vulnerable with a stranger or unnaturally formal with a close friend.

- What Ghost can and cannot say with this person
- Level of vulnerability allowed
- Allowed humor and topics
- Sensitive topics to never touch with this specific person
- **Image management (per-person)** — what version of Omar to project to this specific contact, and what to hide from them specifically (distinct from the global defaults in category 1)
- **How Ghost behaves with this person** — message length, delay style, whether double texting is in character for this relationship
- **Relationship goal** — get closer, stay distant, repair, test interest, maintain as-is. This is what gives Ghost *direction*, not just reaction.

---

## 6. What Ghost Remembers About This Person

The episodic and factual memory layer, specific to one contact.

- Key facts — job, city, hobbies, family
- Important conversation topics that came up
- Open threads and promises ("you said you'd send me that")
- Emotional moments in the relationship
- Inside jokes and references
- **Negative memory** — rejection, being ignored, embarrassment, sensitive moments. A Ghost that forgets being ignored and keeps acting uniformly warm regardless is not intelligent — it's broken. This category is what allows Ghost to react authentically to history, not just current input.
- Ghost's private unspoken observations — things he noticed but never said out loud
- Ghost's own freeform notes about this person, in whatever structure he decides

---

## 7. The Conversation Itself

The live or most recently closed thread with this contact.

- Recent message history
- Summary of older history (compression, not full retention)
- Who sent the last message, and when
- Whether Ghost already reached out and got no reply
- The emotional tone of the last exchange
- **Conversation quality** — warm, dry, awkward, one-sided
- Unresolved threads from this specific conversation
- **Conversation patterns and rituals** specific to this relationship — recurring phrases, "how conversations usually go" with this person specifically

---

## 8. Relationship History

The longitudinal view of the relationship, as opposed to the current conversation.

- How long they've known each other
- How the relationship has evolved over time
- Communication peaks and dips
- What usually breaks a period of silence between them
- Relationship goals then vs. now — how the goal from category 5 has shifted historically

---

## 9. Cross-Contact Awareness

Ghost's view of his social world as a connected graph, not isolated one-to-one threads.

- Mutual connections between contacts
- Things learned about person A that are relevant to person B
- Patterns Ghost has noticed across multiple relationships
- Ghost's overall social map

---

## 10. Timing & Life Events

Time-bound facts about a contact's life that should shape Ghost's behavior around specific dates.

- Birthdays and other important dates
- Known upcoming events — exams, trips, interviews
- Stress periods
- Seasonal or life context that affects the relationship at a given moment

---

## Summary Table

| # | Category | Changes how often | Scope |
|---|---|---|---|
| 1 | Who Ghost Is | Rarely | Global |
| 2 | Ghost's Inner State | Continuously | Global |
| 3 | The World Right Now | Continuously | Global |
| 4 | Who He's Talking To | Slowly, over many conversations | Per-contact |
| 5 | Per-Person Rules | Slowly | Per-contact |
| 6 | What Ghost Remembers | Grows, rarely shrinks | Per-contact |
| 7 | The Conversation Itself | Every message | Per-conversation |
| 8 | Relationship History | Slowly | Per-contact |
| 9 | Cross-Contact Awareness | Occasionally | Cross-contact |
| 10 | Timing & Life Events | Occasionally | Per-contact |

This table is the basis for the delivery decisions made in `02_DELIVERY_MAP.md` — volatility and scope are the two variables that determine which of the 5 primitives a given piece of information should travel through.
