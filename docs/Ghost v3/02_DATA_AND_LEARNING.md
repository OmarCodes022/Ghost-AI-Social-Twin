# 02: Data and learning

Status: done. Decisions D-028 to D-041.

Design rule for this session: it must work for **any** user (any language, any platform, little data, no patience), not just Omar.

## Five kinds of data

| Kind | Test | Includes |
|------|------|----------|
| **Me** | about the subject himself | story, values, opinions, knowledge, his plans |
| **People** | about someone else, or him with someone | who they are, history, inside jokes, their plans |
| **Voice** | how he texts, not what | fingerprint, examples, timing and rhythm |
| **Taste** | things he likes or sends | memes, GIFs, stickers, music, interests |
| **Media** | files he can send | photos, later voice samples |

Tie-break order: a file, Media. How he says it, Voice. About someone else, People. Something he likes or sends, Taste. Otherwise, Me.

Nobody sorts anything: users talk, upload and connect, and Ghost files it. Kinds show up only in the completeness view. Feedback is a source, not a kind.

## Zero friction

Nothing blocks. A Ghost works from minute one and improves as data arrives.

| Level | User did | Ghost can |
|-------|----------|-----------|
| 0 | signed up | chat in the app as a rough version of them, asking as he goes |
| 1 | connected WhatsApp | learn from the history WhatsApp sends to a new linked device (amount: Q-015) |
| 2 | uploaded exports | much deeper draft |
| 3 | rehearsal or interview | identity and opinions filled |
| 4 | weeks of use | learns from every live message |

- Connecting an account **is** the import.
- The app shows how complete a Ghost is, per kind of data ("Voice 80%, Opinions 20%"), so users know what he lacks.
- Texting real contacts at any level is the owner's call.

**Must-know before texting anyone:** name, age, city, language(s).

## Rehearsal (replaces most of the interview)

Ghost texts the owner in the app:
- **Real replays:** a real past moment with the owner's reply hidden. He compares the answer with what was actually said: training and test in one.
- **Gap scenarios:** situations he has no data for.
- **Fact questions**, casually ("who's Youssef to you btw?").

- He picks what to ask from his weakest data and the people he's about to text.
- Started by Ghost or by the owner.
- Any topic can be skipped forever.
- Text or voice answers (voice also gives voice samples).
- Rehearsal answers count a bit less than real messages when they disagree (people answer how they *think* they text).

**Deep interview:** optional, same chat, longer sitting, for people who want a strong Ghost fast. v2's `omar.md` is reference only; the interview is redone in the new flow.

**Shadow mode:** optional. Ghost writes what he would have said next to what the owner said, before going live.

## Strangers with a goal

The owner can mark a contact as a **stranger**, set a **goal** (make a friend, get a date, anything), and let Ghost run free. The goal becomes a long-lived goal signal (D-015).

## Languages

- **A fingerprint per language.** Texting in English and in Franco-Arabic are different styles, not one style translated.
- Franco-Arabic (Arabic in Latin letters and numbers) is its own language.
- Language per contact, and mixing inside a message, are learned per contact: people differ.
- He may text in a language he has little data for; the completeness view shows the gap.

## Live data is the main source

- Exports are the starter. Once connected, every new message is data.
- **The owner's manual replies are the best data there is**: what the subject actually said, live. Gaps vs what Ghost would have said feed learning.
- Old data (years old, not months) weighs a little less than recent data. Mild: history is still most of the context.
- No per-chat exclusion from learning (for now).

## Other people's data

- Contacts' messages are used (D-010). Every fact is tagged with who it came from, so audiences work (D-024).
- Contacts' own style is learned too: it helps predict reactions and seeds their Ghost later.
- Other subjects (real or fictional) use the same pipeline with different sources; details in session 6.

## Photos and media

- An upload area. No camera roll access.
- Ghost describes each photo himself so he can pick one.
- Per photo, or for the whole Ghost: **marked sendable only**, or **free**. Photos have audiences like memories.
- Media friends send is saved, to understand and remember, never resent.
- Voice cloning later from voice samples (rehearsal voice answers, voice notes).

## Sources

| Source | How | He texts there? |
|--------|-----|-----------------|
| WhatsApp | linked device, export files | yes |
| Instagram | data download (JSON), live later | yes, later |
| Snapchat | live (exports keep only saved chats) | yes, later |
| Discord | data package, live | yes |
| Telegram | export, live | maybe |
| Notes, docs, journals | upload | no |
| Social posts | the account | feeds |

## Extraction: chats into a Ghost

Each step uses the cheapest thing that can do it.

| Step | What | Done by |
|------|------|---------|
| 1. Parse | read exports, tell the subject's messages from others' | code |
| 2. Cut | split history into conversations by time gaps | code |
| 3. Fingerprint | lengths, emojis, shortcuts, language mix, timing; per language and per contact | code, no model |
| 4. Example bank | each subject reply with what came before, tagged (contact, language, situation), searchable | code + embeddings |
| 5. Triage | "anything worth remembering here?" | cheap model |
| 6. Understand | Me, People, Taste facts from flagged conversations, tagged by who said it | strong model |
| 7. Connect | merge people across platforms, order facts in time, newest wins | strong model, batched |

- Voice is mostly code: cheap and exact. The strong model reads only conversations that matter.
- Live intake stays on the strong model (D-027): a trickle. Imports are a flood, so they get triage.
- **Same person across platforms:** Ghost links them himself; the owner can also link or unlink.
- **Personas, proposed:** Ghost groups contacts the subject texts the same way and proposes personas. The owner names, approves or ignores them.

## Learning loop

| Source | Strength |
|--------|----------|
| Owner's manual replies | strongest |
| Owner's corrections (typed: what he'd actually say) | strong |
| Rehearsal answers | strong, a bit below real messages |
| New live chats | normal |
| How contacts react | normal |

- **Instantly:** new examples, new facts.
- **In dreams:** fingerprint recount, persona and override tweaks (unlocked fields only), feeling baselines.
- He tells the owner what he learned, lightly and only where it fits naturally (for example, in the rehearsal chat). No reports, no bloat.

**Rule 1: Voice is learned only from the subject's real messages, never from Ghost's own.** His own chats still teach facts. Otherwise small mistakes get copied until he becomes a parody.

**Rule 2: reactions adjust how he handles each person, not who he is.** He spots patterns (Sara ignores voice notes, Ahmed replies more to memes, late texts land badly with Youssef) and adapts timing, topics and format per contact, like a person does. The base voice comes only from Rule 1, so he adapts without turning into a people pleaser. Busted moments ("is this a bot?") also go to the lab and the owner.

## Proving he's you

| Test | Answers | How |
|------|---------|-----|
| **Replay** | does he reply like you? | conversations hidden from him forever; he writes the reply, compared with the real one (fingerprint distance + judge model). Automatic. |
| **Blind pick** | would someone notice? | owner sees real vs Ghost reply and picks. Goal: 50/50. Owner only for now (no disclosure, D-010). |
| **Busted rate** | does it hold live? | how often contacts say "is this a bot", "you sound off" |
| **Fact accuracy** | does he know things? | rehearsal fact questions |

- Completeness (D-028) shows how much he **has**; tests show how **good** he is. The app shows both.
- If replay scores drop after an update, the lab warns the owner. No automatic rollback.

## No fine-tuning (for now)

Examples, fingerprint and memory in the prompt. A fine-tune is frozen while people change daily, can't hold per-contact and per-language styles, and would need one model per Ghost. Revisit in session 7.
