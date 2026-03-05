#!/usr/bin/env python3
"""Ghost admin CLI — manage contacts and knowledge from the terminal.

Usage:
  python scripts/admin.py contact --phone 447xxx [--name Alice] [--tier 1] [--notes "works at Google"]
  python scripts/admin.py remember --phone 447xxx --text "Has a dog called Max"
  python scripts/admin.py me --text "I hate small talk. I never use exclamation marks."
  python scripts/admin.py show --phone 447xxx
  python scripts/admin.py contacts
"""
import argparse
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


# ── contact ────────────────────────────────────────────────────────────────────

def cmd_contact(args):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    tier = int(args.tier) if args.tier else None
    name = args.name or None
    notes = args.notes or None

    cur.execute(
        """
        INSERT INTO contacts (phone_number, name, relationship_tier, notes, last_interaction, created_at)
        VALUES (%s, %s, %s, %s, NOW(), NOW())
        ON CONFLICT (phone_number) DO UPDATE SET
            name              = COALESCE(%s, contacts.name),
            relationship_tier = COALESCE(%s, contacts.relationship_tier),
            notes             = COALESCE(%s, contacts.notes)
        RETURNING phone_number, name, relationship_tier, notes
        """,
        (args.phone, name, tier or 5, notes, name, tier, notes),
    )
    row = dict(cur.fetchone())
    conn.commit()
    cur.close()
    conn.close()

    print(f"✓ {row['phone_number']}  |  name: {row['name']}  |  tier: {row['relationship_tier']}")
    if row["notes"]:
        print(f"  notes: {row['notes']}")


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
    cur.close()
    conn.close()

    print(f"✓ Memory saved for {args.phone}  (id: {chunk_id})")
    print(f'  "{args.text}"')


# ── me ─────────────────────────────────────────────────────────────────────────

def cmd_me(args):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute(
        """
        INSERT INTO knowledge_chunks (category, content, contact_phone, source)
        VALUES ('identity', %s, NULL, 'manual')
        RETURNING id
        """,
        (args.text,),
    )
    chunk_id = cur.fetchone()["id"]
    conn.commit()
    cur.close()
    conn.close()

    print(f"✓ Identity chunk saved  (id: {chunk_id})")
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

    p = sub.add_parser("contact", help="Set contact name, tier, notes")
    p.add_argument("--phone", required=True)
    p.add_argument("--name")
    p.add_argument("--tier", help="1=close friend … 5=stranger")
    p.add_argument("--notes")

    p = sub.add_parser("remember", help="Add a memory about a contact")
    p.add_argument("--phone", required=True)
    p.add_argument("--text", required=True)

    p = sub.add_parser("me", help="Add identity data about yourself")
    p.add_argument("--text", required=True)

    p = sub.add_parser("show", help="Show everything about a contact")
    p.add_argument("--phone", required=True)

    sub.add_parser("contacts", help="List all contacts")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    {"contact": cmd_contact, "remember": cmd_remember, "me": cmd_me,
     "show": cmd_show, "contacts": cmd_contacts}[args.cmd](args)


if __name__ == "__main__":
    main()
