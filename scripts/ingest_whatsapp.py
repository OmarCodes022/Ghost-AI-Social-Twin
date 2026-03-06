#!/usr/bin/env python3
"""Ingest a WhatsApp exported .txt chat file into Ghost knowledge_chunks.

Chunks the conversation into session windows and stores each as a knowledge_chunk
for the contact. Also computes a voice_profile from the contact's message patterns
and saves it to contacts.voice_profile.

Usage:
    make ingest FILE=exports/alice.txt PHONE=33744746977 NAME="Alice"
    # or directly:
    python scripts/ingest_whatsapp.py --file exports/alice.txt --phone 33744746977 [--name Alice] [--my-name Omar]

Export format supported:
    iOS:     [DD/MM/YYYY, HH:MM:SS] Sender: message
    Android: DD/MM/YYYY, HH:MM - Sender: message
"""
import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import boto3
import psycopg2
import psycopg2.extras

REGION = "eu-west-1"
ENV = "dev"

# WhatsApp export line patterns
_IOS_RE = re.compile(
    r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),\s+(\d{1,2}:\d{2}:\d{2}(?:\s*[AP]M)?)\]\s+(.+?):\s+(.+)$"
)
_ANDROID_RE = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{2,4}),\s+(\d{1,2}:\d{2}(?:\s*[AP]M)?)\s+-\s+(.+?):\s+(.+)$"
)

# System messages to skip
_SKIP_PATTERNS = [
    r"Messages and calls are end-to-end encrypted",
    r"<Media omitted>",
    r"image omitted",
    r"video omitted",
    r"audio omitted",
    r"document omitted",
    r"sticker omitted",
    r"GIF omitted",
    r"null",
    r"This message was deleted",
    r"You deleted this message",
    r"^\s*$",
]
_SKIP_RE = re.compile("|".join(_SKIP_PATTERNS), re.IGNORECASE)

# Emoji detection (simplified unicode ranges)
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0000FE00-\U0000FEFF"
    "\U0001FA00-\U0001FA9F\U0001FAA0-\U0001FAFF]+",
    re.UNICODE,
)

SESSION_GAP = timedelta(hours=2)   # new session if gap > 2h
CHUNK_MAX_MSGS = 12                # max messages per knowledge_chunk


def get_conn():
    ssm = boto3.client("ssm", region_name=REGION)
    dsn = ssm.get_parameter(
        Name=f"/ghost/{ENV}/db/connection_string", WithDecryption=True
    )["Parameter"]["Value"]
    return psycopg2.connect(dsn, sslmode="require")


# ── Parsing ────────────────────────────────────────────────────────────────────

def _parse_datetime(date_str: str, time_str: str) -> datetime | None:
    """Try multiple date/time format combos."""
    time_str = time_str.strip()
    date_str = date_str.strip()
    formats = [
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S %p",
        "%d/%m/%Y %I:%M:%S %p",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %I:%M %p",
        "%d/%m/%y %H:%M:%S",
        "%d/%m/%y %H:%M:%S %p",
        "%d/%m/%y %I:%M:%S %p",
        "%d/%m/%y %H:%M",
        "%d/%m/%y %I:%M %p",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%y %H:%M",
        "%m/%d/%y %I:%M %p",
    ]
    combined = f"{date_str} {time_str}"
    for fmt in formats:
        try:
            return datetime.strptime(combined, fmt)
        except ValueError:
            continue
    return None


def parse_export(path: Path) -> list[dict]:
    """Parse a WhatsApp export .txt file into a list of message dicts."""
    messages = []
    current = None

    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw_line in fh:
            line = raw_line.rstrip("\n")

            m = _IOS_RE.match(line) or _ANDROID_RE.match(line)
            if m:
                date_s, time_s, sender, content = m.groups()
                ts = _parse_datetime(date_s, time_s)
                if ts is None:
                    continue
                if _SKIP_RE.search(content):
                    current = None
                    continue
                current = {
                    "ts": ts,
                    "sender": sender.strip(),
                    "content": content.strip(),
                }
                messages.append(current)
            elif current and line.startswith(" ") or (current and not _IOS_RE.match(line) and not _ANDROID_RE.match(line)):
                # Continuation of a multi-line message
                if current and line.strip() and not _SKIP_RE.search(line):
                    current["content"] += " " + line.strip()

    return messages


# ── Chunking ───────────────────────────────────────────────────────────────────

def _split_into_sessions(messages: list[dict]) -> list[list[dict]]:
    """Group messages into sessions separated by SESSION_GAP silences."""
    if not messages:
        return []
    sessions = []
    current_session = [messages[0]]
    for msg in messages[1:]:
        if msg["ts"] - current_session[-1]["ts"] > SESSION_GAP:
            sessions.append(current_session)
            current_session = [msg]
        else:
            current_session.append(msg)
    sessions.append(current_session)
    return sessions


def _session_to_chunks(session: list[dict], contact_name: str, my_name: str) -> list[str]:
    """Convert a session into one or more text chunks."""
    chunks = []
    date_label = session[0]["ts"].strftime("%Y-%m-%d")

    # Split session into sub-chunks of CHUNK_MAX_MSGS messages
    for i in range(0, len(session), CHUNK_MAX_MSGS):
        sub = session[i : i + CHUNK_MAX_MSGS]
        lines = [f"[{date_label}]"]
        for msg in sub:
            # Normalise sender name: contact or "me"
            role = contact_name if msg["sender"] != my_name else "me"
            lines.append(f"{role}: {msg['content']}")
        chunks.append("\n".join(lines))
    return chunks


# ── Voice profile ──────────────────────────────────────────────────────────────

def compute_voice_profile(messages: list[dict], contact_name: str, my_name: str) -> dict:
    """Compute contact's voice profile from their messages."""
    contact_msgs = [m for m in messages if m["sender"] != my_name]
    if not contact_msgs:
        return {}

    lengths = [len(m["content"]) for m in contact_msgs]
    emoji_counts = [len(_EMOJI_RE.findall(m["content"])) for m in contact_msgs]
    has_upper = [any(c.isupper() for c in m["content"]) for m in contact_msgs]

    avg_len = sum(lengths) / len(lengths)
    emoji_rate = sum(emoji_counts) / len(contact_msgs)
    uppercase_rate = sum(has_upper) / len(contact_msgs)

    if avg_len < 40:
        response_style = "very short"
    elif avg_len < 100:
        response_style = "short"
    elif avg_len < 250:
        response_style = "medium"
    else:
        response_style = "long"

    # Approximate formality: ratio of sentences ending with punctuation + capitals
    formal_signals = sum(
        1 for m in contact_msgs
        if m["content"].endswith(".") or m["content"][0:1].isupper()
    )
    formality_score = round(formal_signals / len(contact_msgs), 2)

    return {
        "avg_message_length": round(avg_len),
        "emoji_rate": round(emoji_rate, 3),
        "uppercase_rate": round(uppercase_rate, 2),
        "formality_score": formality_score,
        "response_style": response_style,
        "total_messages_analysed": len(contact_msgs),
    }


# ── DB ─────────────────────────────────────────────────────────────────────────

def ingest(
    conn,
    phone: str,
    contact_name: str,
    chunks: list[str],
    voice_profile: dict,
    dry_run: bool,
) -> int:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Upsert contact name if not already set
    cur.execute(
        """
        INSERT INTO contacts (phone_number, name, relationship_tier, last_interaction, created_at)
        VALUES (%s, %s, 3, NOW(), NOW())
        ON CONFLICT (phone_number) DO UPDATE SET
            name         = COALESCE(contacts.name, EXCLUDED.name),
            voice_profile = %s
        """,
        (phone, contact_name, json.dumps(voice_profile)),
    )

    inserted = 0
    for chunk_text in chunks:
        if dry_run:
            print(f"\n[DRY RUN] Would insert chunk:\n{chunk_text[:200]}...")
            inserted += 1
            continue
        cur.execute(
            """
            INSERT INTO knowledge_chunks (category, content, contact_phone, source)
            VALUES ('relationship', %s, %s, 'import')
            """,
            (chunk_text, phone),
        )
        inserted += 1

    if not dry_run:
        conn.commit()
    cur.close()
    return inserted


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Ingest a WhatsApp .txt export into Ghost knowledge_chunks."
    )
    parser.add_argument("--file", required=True, help="Path to exported .txt file")
    parser.add_argument("--phone", required=True, help="Contact phone number (e.g. 33744746977)")
    parser.add_argument("--name", default=None, help="Contact's display name (as in export)")
    parser.add_argument("--my-name", default="Omar", help="Your name as it appears in export (default: Omar)")
    parser.add_argument("--dry-run", action="store_true", help="Parse and preview without writing to DB")
    args = parser.parse_args()

    export_path = Path(args.file).expanduser()
    if not export_path.exists():
        print(f"✗ File not found: {export_path}")
        sys.exit(1)

    print(f"Parsing {export_path.name} …")
    messages = parse_export(export_path)
    if not messages:
        print("✗ No messages parsed. Check the file format.")
        sys.exit(1)

    # Auto-detect contact name from senders if --name not given
    senders = {m["sender"] for m in messages}
    my_name = args.my_name
    other_senders = senders - {my_name}

    contact_name = args.name
    if not contact_name:
        if len(other_senders) == 1:
            contact_name = other_senders.pop()
            print(f"Auto-detected contact name: {contact_name}")
        else:
            print(f"Found senders: {senders}")
            print("Multiple non-Omar senders detected. Use --name to specify the contact name.")
            sys.exit(1)

    print(f"  {len(messages)} messages parsed")
    print(f"  senders: {senders}")

    # Chunk
    sessions = _split_into_sessions(messages)
    print(f"  {len(sessions)} sessions found")

    all_chunks = []
    for session in sessions:
        all_chunks.extend(_session_to_chunks(session, contact_name, my_name))

    print(f"  {len(all_chunks)} chunks to store")

    # Voice profile
    profile = compute_voice_profile(messages, contact_name, my_name)
    print(f"\nVoice profile for {contact_name}:")
    for k, v in profile.items():
        print(f"  {k}: {v}")

    if args.dry_run:
        print(f"\n[DRY RUN] Would insert {len(all_chunks)} chunks into knowledge_chunks.")
        for chunk in all_chunks[:3]:
            print(f"\n---\n{chunk[:300]}")
        print("\n(use without --dry-run to write to DB)")
        return

    print(f"\nConnecting to DB …")
    conn = get_conn()
    n = ingest(conn, args.phone, contact_name, all_chunks, profile, dry_run=False)
    conn.close()

    print(f"\n✓ {n} chunks stored for {contact_name} ({args.phone})")
    print(f"✓ Voice profile saved to contacts table")


if __name__ == "__main__":
    main()
