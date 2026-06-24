#!/usr/bin/env python3
"""Ghost admin CLI — run via Makefile targets or directly."""
import argparse
import json
import os
import sys
import uuid
from datetime import datetime

import boto3
import psycopg2
import psycopg2.extras

REGION = "eu-west-1"
ENV = os.environ.get("ENV", "dev")


def _get_conn():
    ssm = boto3.client("ssm", region_name=REGION)
    dsn = ssm.get_parameter(
        Name=f"/ghost/{ENV}/db/connection_string", WithDecryption=True
    )["Parameter"]["Value"]
    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def _get_sqs():
    return boto3.client("sqs", region_name=REGION)


def _queue_url(name: str) -> str:
    ssm = boto3.client("ssm", region_name=REGION)
    cf = boto3.client("cloudformation", region_name=REGION)
    stacks = cf.describe_stacks(StackName=f"ghost-{ENV}")["Stacks"][0]["Outputs"]
    mapping = {o["OutputKey"]: o["OutputValue"] for o in stacks}
    return mapping.get("OutboundQueueUrl", "")


# ── contact ───────────────────────────────────────────────────────────────────

def cmd_contact(args):
    conn = _get_conn()
    updates = []
    params = []
    if args.name:
        updates.append("name = %s"); params.append(args.name)
    if args.tier:
        updates.append("relationship_tier = %s"); params.append(int(args.tier))
    if args.notes:
        updates.append("notes = %s"); params.append(args.notes)
    if args.lang:
        updates.append("language_primary = %s"); params.append(args.lang.lower())

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO contacts (phone_number, name, relationship_tier, language_primary,
                                  texting_style, trust_level, risk_level)
            VALUES (%s, %s, %s, %s, '{}', 0.8, 0.1)
            ON CONFLICT (phone_number) DO NOTHING
            """,
            (args.phone, args.name or args.phone, int(args.tier) if args.tier else 3,
             args.lang.lower() if args.lang else "french"),
        )
        if updates:
            params.append(args.phone)
            cur.execute(
                f"UPDATE contacts SET {', '.join(updates)}, updated_at = NOW() WHERE phone_number = %s",
                params,
            )
    conn.commit()
    conn.close()
    print(f"Contact {args.phone} updated.")


# ── show ──────────────────────────────────────────────────────────────────────

def cmd_show(args):
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM contacts WHERE phone_number = %s", (args.phone,))
        contact = cur.fetchone()
        cur.execute("SELECT * FROM contact_state WHERE contact_phone = %s", (args.phone,))
        state = cur.fetchone()
        cur.execute(
            "SELECT content, category, importance FROM memories WHERE contact_phone = %s ORDER BY created_at DESC LIMIT 10",
            (args.phone,)
        )
        memories = cur.fetchall()
    conn.close()

    if not contact:
        print(f"No contact found for {args.phone}")
        return

    print(f"\n=== {contact['name']} ({args.phone}) ===")
    print(f"Tier: {contact['relationship_tier']} | Lang: {contact['language_primary']}")
    print(f"Trust: {contact['trust_level']} | Risk: {contact['risk_level']}")
    if contact.get("notes"):
        print(f"Notes: {contact['notes']}")
    if state:
        print(f"\nState: attitude={state.get('current_attitude_score', 0):.2f} | unanswered={state.get('unanswered_message_flag')}")
    if memories:
        print(f"\nMemories ({len(memories)}):")
        for m in memories:
            print(f"  [{m['category']}] {m['content'][:80]}...")


# ── contacts ──────────────────────────────────────────────────────────────────

def cmd_contacts(args):
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT phone_number, name, relationship_tier, language_primary, trust_level FROM contacts ORDER BY relationship_tier, name"
        )
        rows = cur.fetchall()
    conn.close()
    if not rows:
        print("No contacts.")
        return
    for r in rows:
        print(f"[T{r['relationship_tier']}] {r['name']} ({r['phone_number']}) | {r['language_primary']} | trust={r['trust_level']:.1f}")


# ── remember ──────────────────────────────────────────────────────────────────

def cmd_remember(args):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "ingest"))
    from ghost_ingest_utils import get_db_connection, insert_memory
    conn = get_db_connection()
    insert_memory(conn, args.text, "behavioral", "french", 0.8, contact_phone=args.phone)
    conn.close()
    print(f"Memory saved for {args.phone}.")


# ── me ────────────────────────────────────────────────────────────────────────

def cmd_me(args):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "ingest"))
    from ghost_ingest_utils import get_db_connection, insert_memory
    conn = get_db_connection()
    insert_memory(conn, args.text, "identity", "french", 0.9)
    conn.close()
    print("Identity memory saved.")


# ── send ──────────────────────────────────────────────────────────────────────

def cmd_send(args):
    cf = boto3.client("cloudformation", region_name=REGION)
    outputs = cf.describe_stacks(StackName=f"ghost-{ENV}")["Stacks"][0]["Outputs"]
    queue_url = next(o["OutputValue"] for o in outputs if o["OutputKey"] == "OutboundQueueUrl")

    text = args.text.replace("\\n", "\n")
    sqs = _get_sqs()
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps({"to_phone_number": args.phone, "content": text}),
        MessageGroupId=args.phone,
        MessageDeduplicationId=str(uuid.uuid4()),
    )
    print(f"Queued message to {args.phone}: {text[:60]}")


# ── mood ──────────────────────────────────────────────────────────────────────

def cmd_mood(args):
    conn = _get_conn()
    with conn.cursor() as cur:
        if args.reset:
            cur.execute(
                "UPDATE ghost_state SET mood = 'neutral', social_battery = 0.7, emotional_load = 0.3, whats_on_mind = NULL, updated_at = NOW() WHERE id = 1"
            )
            conn.commit()
            print("Ghost state reset.")
            conn.close()
            return

        updates = []
        params = []
        if args.notes:
            updates.append("whats_on_mind = %s"); params.append(args.notes)
        if args.energy:
            updates.append("social_battery = %s"); params.append(float(args.energy))
        if args.availability:
            updates.append("mood = %s"); params.append(args.availability)

        if updates:
            cur.execute(
                f"UPDATE ghost_state SET {', '.join(updates)}, updated_at = NOW() WHERE id = 1",
                params,
            )
            conn.commit()

        cur.execute("SELECT mood, social_battery, emotional_load, whats_on_mind FROM ghost_state WHERE id = 1")
        row = cur.fetchone()
    conn.close()
    if row:
        print(f"Mood: {row['mood']} | Battery: {row['social_battery']:.1f} | Load: {row['emotional_load']:.1f}")
        if row["whats_on_mind"]:
            print(f"On mind: {row['whats_on_mind']}")


# ── proactive ─────────────────────────────────────────────────────────────────

def cmd_proactive(args):
    phones = [p.strip() for p in args.phones.split(",") if p.strip()]
    cf = boto3.client("cloudformation", region_name=REGION)
    outputs = cf.describe_stacks(StackName=f"ghost-{ENV}")["Stacks"][0]["Outputs"]
    heartbeat_url = next(
        (o["OutputValue"] for o in outputs if "Heartbeat" in o.get("OutputKey", "")), None
    )
    if not heartbeat_url:
        print("HeartbeatQueue URL not in stack outputs — add it to template.yaml Outputs.")
        return

    sqs = _get_sqs()
    for phone in phones:
        payload = {"phone": phone, "reason": "proactive_admin", "condition_id": None}
        if args.dry_run:
            print(f"[DRY RUN] Would enqueue heartbeat for {phone}")
        else:
            sqs.send_message(QueueUrl=heartbeat_url, MessageBody=json.dumps(payload))
            print(f"Heartbeat queued for {phone}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(prog="admin")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("contact")
    p.add_argument("--phone", required=True)
    p.add_argument("--name"); p.add_argument("--tier"); p.add_argument("--notes")
    p.add_argument("--lang"); p.add_argument("--persona"); p.add_argument("--persona-name")

    p = sub.add_parser("show")
    p.add_argument("--phone", required=True)

    sub.add_parser("contacts")

    p = sub.add_parser("remember")
    p.add_argument("--phone", required=True); p.add_argument("--text", required=True)

    p = sub.add_parser("me")
    p.add_argument("--text", required=True); p.add_argument("--persona")

    p = sub.add_parser("send")
    p.add_argument("--phone", required=True); p.add_argument("--text", required=True)

    p = sub.add_parser("mood")
    p.add_argument("--notes"); p.add_argument("--availability"); p.add_argument("--energy")
    p.add_argument("--reset", action="store_true")

    p = sub.add_parser("proactive")
    p.add_argument("--phones", required=True); p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    dispatch = {
        "contact": cmd_contact, "show": cmd_show, "contacts": cmd_contacts,
        "remember": cmd_remember, "me": cmd_me, "send": cmd_send,
        "mood": cmd_mood, "proactive": cmd_proactive,
    }
    fn = dispatch.get(args.command)
    if not fn:
        parser.print_help(); sys.exit(1)
    fn(args)


if __name__ == "__main__":
    main()
