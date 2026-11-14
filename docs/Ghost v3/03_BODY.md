# 03: Body

Status: in progress. Covers so far: channels, connections, senses, acting human (D-042 to D-047).
Still to come: group chats, ban risk (Q-003), tool catalog (Q-013).

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
