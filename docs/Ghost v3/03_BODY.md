# 03: Body

Status: done. Decisions D-042 to D-050.

The mind decides **what**. The body decides **how it lands** on each platform and what he can **sense** there.

**Ghost is better than his subject.** He acts like him, but is never limited to human senses or abilities (D-047).

## Channels as plug-ins

```
WhatsApp adapter ──┐
Instagram adapter ─┼──> common events  ──> senses / intake
Snap adapter ──────┤
Discord adapter ───┤ <── common actions <── Heartbeat
App chat ──────────┘
```

- Each adapter is a small separate piece that wraps whatever that platform needs (Baileys for WhatsApp, something else elsewhere) and translates it to and from one common contract. The library never leaks past the adapter.
- **Common events** (in): message, voice note, media, reaction, typing, online, read, edited, deleted, story, call.
- **Common actions** (out): send text or media, react, quote-reply, typing, mark read, presence, edit, delete.
- Each adapter declares what it **can** do; the mind only uses what the platform supports.
- Adding a platform = writing one adapter. Ghost doesn't change.

**Where he replies:** always on the platform they texted him on. For outreach Ghost picks, usually the platform most active with that contact.

## Connections

- Connect by QR or pairing code (WhatsApp), or login (Instagram, Discord). Ask for full history on connect; WhatsApp's server decides how much, so it's measured when we build (Q-015). Exports fill the gaps.
- **When a connection drops:** the app shows it and that the owner is now in control. The app is the only notification.
- **A drop pauses Ghost for every affected person on all platforms.** If Sara is on WhatsApp and Instagram and WhatsApp drops, Ghost stops texting Sara everywhere, because she may have written on WhatsApp and he'd answer on Instagram without knowing.
- A dedicated Ghost number lives in a phone like any number (WhatsApp logs linked devices out after about 14 days of phone inactivity).

## What he senses

Everything, and more than a human:

| Thing | How |
|-------|-----|
| Text, emojis, quote replies | directly |
| Voice notes | transcribed, plus tone |
| Photos, screenshots, memes | vision |
| Stickers, GIFs | described once, remembered by ID |
| Videos | frames, plus audio |
| Reactions | events |
| Edits | the before and after |
| **Deleted messages** | **the content**, whenever the platform delivers it |
| Typing, online, read | presence senses |
| Stories, status | feeds |
| Calls | an event; Ghost decides: ignore, decline, or text |

## Acting human

Every behaviour comes from his fingerprint and feelings, never a fixed rule (D-018).

| Behaviour | Driven by |
|-----------|-----------|
| Reply delay | subject's reply speed per contact and time of day, plus mood, energy, busy |
| Read receipts | his choice: now, later, or leave on read |
| Presence | online when "picking up the phone", never 24/7 |
| Typing indicator | as long as the subject would take to type it, with pauses |
| Bubbles | thoughts split like the subject splits them, realistic gaps |
| Typos | the subject's usual shortcuts **and** real slips, sometimes fixed with `*word` |
| Edits, deletes | rare ("wrong chat lol") |
| Reactions instead of replies | when that's what the subject would do |
| Quote replies | to a specific old message when it fits |
| Stickers, GIFs, memes as answers | from Taste |
| Late replies | "sorry just saw this" days later, when it fits |
| Double texting, forwarding memes | from fingerprint |
| Voice notes when lazy | once voice cloning exists |

**He has his own life and can lie.** "Sorry, was at the gym." Every excuse or invented plan is saved as a memory with an audience, so he stays consistent with whoever he told.

## Group chats

- A group is assigned like a contact: Ghost + persona + overrides (D-012).
- How active he is comes from the subject's fingerprint **in that group**.
- Mentions, replies to him and questions to him are strong signals.
- **Secrets:** he only says what every member may hear (D-024). The strictest member sets the line.
- He can carry a group moment into a DM.
- Group messages feed People memory for every member.
- He joins, leaves and creates groups himself.

## Not getting banned (light for now)

Being human already covers most of it: sleep (D-019), delays and typing (D-045), no templates (D-018).

- **Account health watch** (reflex): compares activity per account with the subject's own normal range (messages per hour, new people per day, blocks). Above it, the app **warns** the owner. It does not slow Ghost down.
- Bans and restrictions show in the app like a dropped connection (D-043).
- Kept minimal while Omar is the only tester; revisit when scaling (Q-003).

## Tools

| Area | Tools |
|------|-------|
| Memory | search (RAG), query (SQL), remember, update, supersede, link people across platforms |
| Mind | write, edit, drop signals; adjust feelings; set goals; notes to self; sleep and wake; "check back when..." conditions |
| Talk | text, bubbles, uploaded media, GIF and sticker search, react, quote reply, edit, delete, forward, read or leave unread, typing, presence, decline a call; voice notes later |
| Groups | join, leave, create, add people |
| World | web search, read a page, news, contacts' stories and posts, profiles and status, weather, time zones, holidays and birthdays |
| Owner | message the owner in the app, ask a question, mention what he learned |
| Self-made | his own tables and queries, small scripts in a sandbox, ask for a new tool |

- He builds freely inside his sandbox (only his own data).
- Tools that reach outside (new platform actions, money, outside services) he asks for; the owner approves (session 4).
