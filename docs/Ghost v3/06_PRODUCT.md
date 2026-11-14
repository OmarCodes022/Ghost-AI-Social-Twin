# 06: Product

Status: done. Decisions D-064 to D-072. The screens get refined in the prototype (6b).

The app people use: a normal chat app where Ghost lives, plus the controls from sessions 2 and 4.

## Platforms

A **native mobile app** and a **web version**, with the same features. The heavy parts (Ghost, adapters) live on servers, so both are windows into the same thing.

## Talking to Ghost

Two places, because they're two jobs.

| | **Ghost chat** | **Command** |
|---|---|---|
| Where | pinned at the top of Chats, like a contact | a button on every screen, opens over it |
| He is | in character: your twin, his voice, his mood | out of character: a plain, exact assistant |
| For | talking, venting, his opinion, getting to know him | "tell Sara I'll be late", "pause family", "what do you know about Youssef?", "why did you say that to Mom?", new rules, new personas |
| Shows | bubbles | his steps as he works, cards (person, draft, memory, rule), confirm before anything big |
| Context | the chat | where it was opened: inside Sara's chat, "tell her" means Sara |

Your other Ghosts, and Ghosts friends shared with you, are contacts in Chats too. Mixing both in one chat would force him in and out of character and make orders ambiguous; showing his steps is what builds trust.

## Needs you

One queue for everything waiting on the owner. Push notifications open here.
- Drafts in ask first: send, edit, skip.
- His questions.
- Tool requests (D-050).
- Warnings: dropped connection, account health (D-043, D-049).
- Rehearsal cards: "Ahmed said X, I'd say Y. Right?" (D-029).

## Layout

| Tab | What's there |
|-----|--------------|
| **Chats** | every conversation from every platform, Ghosts pinned on top. Each chat shows who handles it: you, Ghost, paused, ask first. |
| **Needs you** | the queue, with a badge |
| **People** | everyone merged across platforms. Per person: Ghost and persona, mode, rules, overrides, what he knows |
| **You** | Ghosts (completeness and quality), Personas, Accounts, Media, Rules, settings |
| *(everywhere)* | Command |

## First 5 minutes

1. Sign up.
2. Basics: name, age, city, languages (D-030).
3. Connect WhatsApp with a pairing code; history starts pulling in.
4. Meet your Ghost in his chat: rough, saying what he's learning, starting a short rehearsal.
5. Pick who he handles.
6. Done. Exports, interview, other platforms are offered later, never required.

## Trust ladder

Every contact starts on **ask first**, including strangers. Ghost **earns auto** person by person: when the owner keeps sending his drafts unedited, he offers in Needs you ("you sent my last 10 to Sara unchanged. Want me to handle her?"). One tap. When to offer is his judgment, not a fixed count (D-018).

Starting on off teaches him nothing; starting on auto risks one bad message to Mom on day one.

## Ghosts of other people

**No limits** (resolves Q-004). A Ghost of someone else can text anyone as that person, like the owner's own Ghost. App store rules and impersonation laws get checked before a public launch (Q-018); that check doesn't shape the design.

## Learning exclusion

The owner can exclude any chat or contact from learning. Learning is on by default (resolves Q-016).

## Sharing

- **Persona library:** share a persona or publish it. Personas hold only style (D-004), so they're safe to share.
- **Share a Ghost:** let chosen people chat with your Ghost inside the app.

## Money

Later. Free during personal testing.

## Prototype (6b)

Before architecture, because the screens decide what the backend serves. Built on a design canvas, refined by Omar (likely in Claude Design):
1. Screen spec from this doc, with every state (empty, loading, waiting, paused, error).
2. Fake but real-feeling data: an owner, ~15 contacts, chats in English and Franco-Arabic, drafts waiting, a paused contact, a dropped account.
3. One round to pick the look and feel.
4. Flows as scenarios: first 5 minutes, a normal day with drafts and Ghost earning auto, owner jumping in, Command, creating and sharing a Ghost of someone else.
5. Gaps found go into OPEN_QUESTIONS; screens get fixed.
6. Mobile first, then web.
