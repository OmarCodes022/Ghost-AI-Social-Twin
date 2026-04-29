#!/usr/bin/env python3
"""Ghost admin CLI — manage contacts and knowledge from the terminal.

Usage:
  python scripts/admin.py contact --phone 447xxx [--name Alice] [--tier 1] [--notes "works at Google"] [--lang French] [--persona lea] [--persona-name "Léa"]
  python scripts/admin.py remember --phone 447xxx --text "Has a dog called Max"
  python scripts/admin.py me --text "I hate small talk. I never use exclamation marks." [--persona default]
  python scripts/admin.py show --phone 447xxx
  python scripts/admin.py contacts
  python scripts/admin.py mood [--notes "bad week"] [--availability minimal] [--energy 0.4] [--reset]
"""
import argparse
import json
import sys

import boto3
import psycopg2
import psycopg2.extras

REGION = "eu-west-1"
ENV = "dev"


def get_conn():
    ssm = boto3.client("ssm", region_name=REGION)
    dsn = ssm.get_parameter(
        Name=f"/ghost/{ENV}/db/connection_string", WithDecryption=True
    )["Parameter"]["Value"]
    return psycopg2.connect(dsn, sslmode="require")


def _embed_text(text: str) -> list[float] | None:
    """Generate embedding via Bedrock Titan v2. Silently skips if unavailable."""
    try:
        br = boto3.client("bedrock-runtime", region_name=REGION)
        resp = br.invoke_model(
            modelId="amazon.titan-embed-text-v2:0",
            body=json.dumps({"inputText": text[:8192]}),
            contentType="application/json",
            accept="application/json",
        )
        return json.loads(resp["body"].read())["embedding"]
    except Exception as exc:
        print(f"  ⚠ embedding skipped ({exc})")
        return None


# ── contact ────────────────────────────────────────────────────────────────────

def cmd_contact(args):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    tier = int(args.tier) if args.tier else None
    name = args.name or None
    notes = args.notes or None
    lang = args.lang or None
    persona = args.persona or None
    persona_name = args.persona_name or None

    # Build voice_profile patch if any profile-related flags provided
    voice_profile_patch = None
    if lang or persona or persona_name:
        import json as _json
        # Merge with existing voice_profile
        cur.execute("SELECT voice_profile FROM contacts WHERE phone_number = %s", (args.phone,))
        row = cur.fetchone()
        existing = dict(row["voice_profile"]) if row and row["voice_profile"] else {}
        if lang:
            existing["preferred_language"] = lang
        if persona:
            existing["persona"] = persona
        if persona_name:
            existing["persona_name"] = persona_name
        voice_profile_patch = _json.dumps(existing)

    cur.execute(
        """
        INSERT INTO contacts (phone_number, name, relationship_tier, notes, last_interaction, created_at)
        VALUES (%s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT (phone_number) DO UPDATE SET
            name              = COALESCE(%s, contacts.name),
            relationship_tier = COALESCE(%s, contacts.relationship_tier),
            notes             = COALESCE(%s, contacts.notes),
            voice_profile     = CASE WHEN %s::jsonb IS NOT NULL
                                     THEN COALESCE(contacts.voice_profile, '{}'::jsonb) || %s::jsonb
                                     ELSE contacts.voice_profile END
        RETURNING phone_number, name, relationship_tier, notes, voice_profile
        """,
        (args.phone, name, tier or 5, notes, name, tier, notes, voice_profile_patch, voice_profile_patch),
    )
    row = dict(cur.fetchone())
    conn.commit()
    cur.close()
    conn.close()

    print(f"✓ {row['phone_number']}  |  name: {row['name']}  |  tier: {row['relationship_tier']}")
    if row["notes"]:
        print(f"  notes: {row['notes']}")
    if row["voice_profile"]:
        vp = row["voice_profile"]
        if vp.get("preferred_language"):
            print(f"  preferred_language: {vp['preferred_language']}")
        if vp.get("persona"):
            print(f"  persona: {vp['persona']}", end="")
            if vp.get("persona_name"):
                print(f"  ({vp['persona_name']})", end="")
            print()


# ── remember ───────────────────────────────────────────────────────────────────

def cmd_remember(args):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        INSERT INTO knowledge_chunks (category, content, contact_phone, source)
        VALUES ('relationship', %s, %s, 'manual')
        RETURNING id
        """,
        (args.text, args.phone),
    )
    chunk_id = cur.fetchone()["id"]
    conn.commit()

    embedding = _embed_text(args.text)
    if embedding:
        cur2 = conn.cursor()
        cur2.execute("UPDATE knowledge_chunks SET embedding = %s::vector WHERE id = %s", (str(embedding), chunk_id))
        conn.commit()
        cur2.close()

    cur.close()
    conn.close()

    print(f"✓ Memory saved for {args.phone}  (id: {chunk_id}){' + embedded' if embedding else ''}")
    print(f'  "{args.text}"')


# ── me ─────────────────────────────────────────────────────────────────────────

def cmd_me(args):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    persona = args.persona or "default"

    cur.execute(
        """
        INSERT INTO knowledge_chunks (category, content, contact_phone, source, persona)
        VALUES ('identity', %s, NULL, 'manual', %s)
        RETURNING id
        """,
        (args.text, persona),
    )
    chunk_id = cur.fetchone()["id"]
    conn.commit()

    embedding = _embed_text(args.text)
    if embedding:
        cur2 = conn.cursor()
        cur2.execute("UPDATE knowledge_chunks SET embedding = %s::vector WHERE id = %s", (str(embedding), chunk_id))
        conn.commit()
        cur2.close()

    cur.close()
    conn.close()

    print(f"✓ Identity chunk saved  (id: {chunk_id})  [persona: {persona}]{' + embedded' if embedding else ''}")
    print(f'  "{args.text}"')


# ── show ───────────────────────────────────────────────────────────────────────

def cmd_show(args):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT * FROM contacts WHERE phone_number = %s",
        (args.phone,),
    )
    contact = cur.fetchone()
    if not contact:
        print(f"No contact found for {args.phone}")
        sys.exit(1)

    print(f"\n── Contact: {args.phone} ──")
    for k, v in dict(contact).items():
        if v is not None:
            print(f"  {k}: {v}")

    cur.execute(
        """
        SELECT category, content, created_at
        FROM knowledge_chunks
        WHERE contact_phone = %s
        ORDER BY created_at DESC
        """,
        (args.phone,),
    )
    chunks = cur.fetchall()
    if chunks:
        print(f"\n── Memories ({len(chunks)}) ──")
        for c in chunks:
            print(f"  [{c['category']}] {c['content']}")

    cur.close()
    conn.close()


# ── mood ───────────────────────────────────────────────────────────────────────

def cmd_mood(args):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if args.reset:
        cur.execute(
            "UPDATE ghost_state SET social_battery = 1.0, emotional_load = 0.0, notes = NULL, updated_at = NOW() WHERE id = 1"
        )
        conn.commit()
        print("✓ Mood reset: social_battery=1.0, emotional_load=0.0, notes cleared")
    else:
        updates = []
        params = []
        if args.notes is not None:
            updates.append("notes = %s")
            params.append(args.notes)
        if args.availability is not None:
            valid = {"deep", "light", "minimal"}
            if args.availability not in valid:
                print(f"Error: --availability must be one of {sorted(valid)}")
                sys.exit(1)
            updates.append("availability = %s")
            params.append(args.availability)
        if args.energy is not None:
            updates.append("energy = %s")
            params.append(float(args.energy))

        if updates:
            params.append(None)  # placeholder for WHERE id = 1
            cur.execute(
                f"UPDATE ghost_state SET {', '.join(updates)}, updated_at = NOW() WHERE id = 1",
                params[:-1],
            )
            conn.commit()
            print(f"✓ Mood updated: {', '.join(updates)}")

    # Always show current state
    cur.execute("SELECT energy, social_battery, emotional_load, availability, notes, updated_at FROM ghost_state WHERE id = 1")
    row = dict(cur.fetchone())
    cur.close()
    conn.close()

    print(f"\n── Ghost state ──")
    print(f"  energy:         {row['energy']:.2f}")
    print(f"  social_battery: {row['social_battery']:.2f}")
    print(f"  emotional_load: {row['emotional_load']:.2f}")
    print(f"  availability:   {row['availability']}")
    print(f"  notes:          {row['notes'] or '—'}")
    print(f"  updated_at:     {str(row['updated_at'])[:19]}")


# ── send ───────────────────────────────────────────────────────────────────────

def cmd_send(args):
    import json as _json
    import uuid as _uuid

    lambda_client = boto3.client("lambda", region_name=REGION)
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get or create conversation
    cur.execute(
        "SELECT id FROM conversations WHERE contact_phone = %s AND arc_state IN ('open', 'flowing') ORDER BY last_message_at DESC LIMIT 1",
        (args.phone,),
    )
    row = cur.fetchone()
    if row:
        conv_id = str(row["id"])
    else:
        conv_id = str(_uuid.uuid4())
        cur.execute(
            "INSERT INTO conversations (id, contact_phone, arc_state, started_at, last_message_at, message_count) VALUES (%s, %s, 'open', NOW(), NOW(), 1)",
            (conv_id, args.phone),
        )

    msg_id = str(_uuid.uuid4())
    cur.execute(
        "INSERT INTO messages (id, conversation_id, role, content, sent_at, was_delayed, delay_seconds, confidence_score, escalated) VALUES (%s, %s, 'agent', %s, NOW(), false, 0, 1.0, false)",
        (msg_id, conv_id, args.text),
    )
    cur.execute("UPDATE conversations SET last_message_at = NOW(), message_count = message_count + 1 WHERE id = %s", (conv_id,))
    conn.commit()
    cur.close()
    conn.close()

    parts = [p.strip() for p in args.text.split("\n") if p.strip()]
    for i, part in enumerate(parts):
        lambda_client.invoke(
            FunctionName=f"ghost-whatsapp-sender-{ENV}",
            InvocationType="Event",
            Payload=_json.dumps({
                "to_phone_number": args.phone,
                "message": part,
                "message_id": msg_id if i == 0 else None,
                "part_index": i,
            }).encode(),
        )

    print(f"✓ sent {len(parts)} part(s) to {args.phone}")
    for p in parts:
        print(f'  "{p}"')


# ── proactive ──────────────────────────────────────────────────────────────────

def cmd_proactive(args):
    """Generate and send a proactive check-in to one or more contacts."""
    import json as _json
    import uuid as _uuid

    phones = [p.strip() for p in args.phones.split(",")]

    ssm = boto3.client("ssm", region_name=REGION)
    api_key = ssm.get_parameter(
        Name=f"/ghost/{ENV}/anthropic/api_key", WithDecryption=True
    )["Parameter"]["Value"]

    try:
        import anthropic as _anthropic
    except ImportError:
        print("Error: anthropic not installed. Run: pip install anthropic")
        sys.exit(1)

    client = _anthropic.Anthropic(api_key=api_key)
    lambda_client = boto3.client("lambda", region_name=REGION)
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Identity chunks (same for all contacts)
    cur.execute(
        """
        SELECT content FROM knowledge_chunks
        WHERE contact_phone IS NULL AND category = 'identity' AND persona = 'default'
        ORDER BY created_at ASC
        """
    )
    identity_chunks = [r["content"] for r in cur.fetchall()]

    for phone in phones:
        cur.execute("SELECT * FROM contacts WHERE phone_number = %s", (phone,))
        contact = cur.fetchone()
        if not contact:
            print(f"✗ {phone}: not found")
            continue

        contact_name = contact["name"] or phone
        voice_profile = dict(contact["voice_profile"]) if contact["voice_profile"] else {}
        persona_name = voice_profile.get("persona_name", "Omar")
        preferred_lang = voice_profile.get("preferred_language")
        lang_rule = (
            f"Write in {preferred_lang}."
            if preferred_lang
            else "Write in the same language as the conversation history, or French if no history."
        )

        # Recent memories
        cur.execute(
            """
            SELECT content FROM knowledge_chunks
            WHERE contact_phone = %s ORDER BY created_at DESC LIMIT 5
            """,
            (phone,),
        )
        memories = [r["content"] for r in cur.fetchall()]

        # Recent history
        cur.execute(
            """
            SELECT m.role, m.content FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE c.contact_phone = %s
            ORDER BY m.sent_at DESC LIMIT 15
            """,
            (phone,),
        )
        history = list(reversed([dict(r) for r in cur.fetchall()]))

        system_lines = [
            f"You are Ghost — an AI standing in for {persona_name} in private WhatsApp conversations.",
            f"Respond exactly as {persona_name} would. Never reveal you are an AI.",
            f"LANGUAGE: {lang_rule}",
            f"Apply {persona_name}'s casual style (short, lowercase, minimal punctuation, slang) in whatever language you use.",
            "",
            "## Your task",
            f"You haven't spoken to {contact_name} in a while. Reach out naturally — reference something you know about them, share a thought, or just a genuine check-in. Keep it real and casual. Don't be dramatic about the silence.",
            "If there's genuinely nothing natural to say, reply with exactly: [skip]",
            "",
            "## Formatting rules",
            "- Split into short natural messages using a newline between each part.",
            "- Each line = one WhatsApp message. Keep each line very short.",
            "- Lowercase only. Minimal punctuation. No emojis unless sparingly used.",
            "- Output ONLY the message text or [skip]. No preamble, labels, or quotes.",
            "",
        ]
        if identity_chunks:
            system_lines += [f"## {persona_name}'s personality and style"] + identity_chunks + [""]
        if memories:
            system_lines += [f"## What you know about {contact_name}"] + [f"- {m}" for m in memories] + [""]

        messages: list[dict] = []
        for row in history:
            role = "assistant" if row["role"] == "agent" else "user"
            messages.append({"role": role, "content": row["content"]})
        while messages and messages[0]["role"] == "assistant":
            messages.pop(0)
        if not messages:
            messages = [{"role": "user", "content": f"[{contact_name} is waiting for you to reach out]"}]
        if messages[-1]["role"] == "assistant":
            messages.append({"role": "user", "content": "[it's your turn to reach out]"})

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            system="\n".join(system_lines),
            messages=messages,
        )
        reply = response.content[0].text.strip()

        if reply.lower().startswith("[skip]"):
            print(f"↷ {phone} ({contact_name}): skipped")
            continue

        print(f"\n── {phone} ({contact_name}) ──")
        print(f"  draft: {reply!r}")

        if not args.dry_run:
            # Get or create conversation
            cur.execute(
                """
                SELECT id FROM conversations
                WHERE contact_phone = %s AND arc_state IN ('open', 'flowing')
                ORDER BY last_message_at DESC LIMIT 1
                """,
                (phone,),
            )
            row = cur.fetchone()
            if row:
                conv_id = str(row["id"])
            else:
                conv_id = str(_uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO conversations
                        (id, contact_phone, arc_state, started_at, last_message_at, message_count)
                    VALUES (%s, %s, 'open', NOW(), NOW(), 1)
                    """,
                    (conv_id, phone),
                )

            msg_id = str(_uuid.uuid4())
            cur.execute(
                """
                INSERT INTO messages
                    (id, conversation_id, role, content, sent_at,
                     was_delayed, delay_seconds, confidence_score, escalated)
                VALUES (%s, %s, 'agent', %s, NOW(), false, 0, 1.0, false)
                """,
                (msg_id, conv_id, reply),
            )
            cur.execute(
                "UPDATE conversations SET last_message_at = NOW(), message_count = message_count + 1 WHERE id = %s",
                (conv_id,),
            )
            conn.commit()

            parts = [p.strip() for p in reply.split("\n") if p.strip()]
            for i, part in enumerate(parts):
                lambda_client.invoke(
                    FunctionName=f"ghost-whatsapp-sender-{ENV}",
                    InvocationType="Event",
                    Payload=_json.dumps({
                        "to_phone_number": phone,
                        "message": part,
                        "message_id": msg_id if i == 0 else None,
                        "part_index": i,
                    }).encode(),
                )
            print(f"  → sent {len(parts)} part(s)")
        else:
            print("  (dry run — not sent)")

    cur.close()
    conn.close()


# ── contacts ───────────────────────────────────────────────────────────────────

def cmd_contacts(args):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        "SELECT phone_number, name, relationship_tier, last_interaction FROM contacts ORDER BY last_interaction DESC"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        print("No contacts yet.")
        return

    print(f"\n{'PHONE':<20} {'NAME':<20} {'TIER':<6} {'LAST SEEN'}")
    print("─" * 65)
    for r in rows:
        name = r["name"] or "—"
        last = str(r["last_interaction"])[:16] if r["last_interaction"] else "—"
        print(f"{r['phone_number']:<20} {name:<20} {r['relationship_tier']:<6} {last}")


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(prog="admin")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("contact", help="Set contact name, tier, notes, language, persona")
    p.add_argument("--phone", required=True)
    p.add_argument("--name")
    p.add_argument("--tier", help="1=close friend … 5=stranger")
    p.add_argument("--notes")
    p.add_argument("--lang", help="Preferred language, e.g. French, Arabic, English")
    p.add_argument("--persona", help="Identity persona slug to use for this contact, e.g. default, lea")
    p.add_argument("--persona-name", help="Display name for the persona, e.g. Léa")

    p = sub.add_parser("remember", help="Add a memory about a contact")
    p.add_argument("--phone", required=True)
    p.add_argument("--text", required=True)

    p = sub.add_parser("me", help="Add identity data about yourself (or a persona)")
    p.add_argument("--text", required=True)
    p.add_argument("--persona", default="default", help="Persona slug this chunk belongs to (default: 'default')")

    p = sub.add_parser("show", help="Show everything about a contact")
    p.add_argument("--phone", required=True)

    sub.add_parser("contacts", help="List all contacts")

    p = sub.add_parser("send", help="Manually send a WhatsApp message as Ghost")
    p.add_argument("--phone", required=True)
    p.add_argument("--text", required=True, help="Message text. Use \\n to split into multiple bubbles.")

    p = sub.add_parser("proactive", help="Send a proactive check-in to one or more contacts")
    p.add_argument("--phones", required=True, help="Comma-separated phone numbers, e.g. 33652469989,33664970571")
    p.add_argument("--dry-run", action="store_true", help="Generate message but don't send")

    p = sub.add_parser("mood", help="Show or update Ghost's persistent mood state")
    p.add_argument("--notes", help="Free-text context: 'bad week', 'just got back from holiday'")
    p.add_argument("--availability", help="deep / light / minimal")
    p.add_argument("--energy", type=float, help="Energy level 0.0–1.0")
    p.add_argument("--reset", action="store_true", help="Reset social_battery=1.0, emotional_load=0.0, clear notes")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    {"contact": cmd_contact, "remember": cmd_remember, "me": cmd_me,
     "show": cmd_show, "contacts": cmd_contacts, "mood": cmd_mood,
     "send": cmd_send, "proactive": cmd_proactive}[args.cmd](args)


if __name__ == "__main__":
    main()
