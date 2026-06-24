#!/usr/bin/env python3
"""
Ingest WhatsApp export .txt files into Ghost v2 DB.

Produces simultaneously:
  - omar_voice_profiles (upsert per language)
  - omar_few_shots (Omar's reply turns as examples)
  - contacts + contact_state + per_person_rules stubs
  - contact_knowledge_gaps for unknown fields

Usage:
    ENV=dev python ingest_whatsapp.py --omar-name "Omar" export1.txt export2.txt
"""
import argparse
import re
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import boto3
import psycopg2
import psycopg2.extras

REGION = "eu-west-1"

_IOS_RE = re.compile(r"^\[(\d{1,2}/\d{1,2}/\d{2,4}),\s+(\d{1,2}:\d{2}:\d{2}(?:\s*[AP]M)?)\]\s+(.+?):\s+(.+)$")
_ANDROID_RE = re.compile(r"^(\d{1,2}/\d{1,2}/\d{2,4}),\s+(\d{1,2}:\d{2}(?:\s*[AP]M)?)\s+-\s+(.+?):\s+(.+)$")
_SKIP_RE = re.compile(r"<Media omitted>|image omitted|video omitted|audio omitted|sticker omitted|GIF omitted|This message was deleted|You deleted this message|Messages and calls are end-to-end encrypted|null", re.IGNORECASE)
_EMOJI_RE = re.compile("[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0001FA00-\U0001FAFF]+", re.UNICODE)


def get_conn():
    ssm = boto3.client("ssm", region_name=REGION)
    env = __import__("os").environ["ENV"]
    dsn = ssm.get_parameter(Name=f"/ghost/{env}/db/connection_string", WithDecryption=True)["Parameter"]["Value"]
    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def _parse_dt(date_s: str, time_s: str) -> datetime | None:
    combined = f"{date_s.strip()} {time_s.strip()}"
    for fmt in ["%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S %p", "%d/%m/%Y %I:%M:%S %p",
                "%d/%m/%Y %H:%M", "%d/%m/%Y %I:%M %p", "%d/%m/%y %H:%M:%S", "%d/%m/%y %H:%M",
                "%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M"]:
        try:
            return datetime.strptime(combined, fmt)
        except ValueError:
            continue
    return None


def parse_export(path: Path) -> list:
    messages = []
    current = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            m = _IOS_RE.match(line) or _ANDROID_RE.match(line)
            if m:
                date_s, time_s, sender, content = m.groups()
                if _SKIP_RE.search(content):
                    current = None
                    continue
                ts = _parse_dt(date_s, time_s)
                if not ts:
                    continue
                current = {"ts": ts, "sender": sender.strip(), "content": content.strip()}
                messages.append(current)
            elif current and line.strip() and not _SKIP_RE.search(line):
                current["content"] += " " + line.strip()
    return messages


def _detect_language(text: str) -> str:
    try:
        from langdetect import detect
        lang = detect(text)
        if lang == "fr":
            return "french"
        if lang == "ar":
            return "arabic"
        return "english"
    except Exception:
        return "english"


def _estimate_tier(total_messages: int) -> int:
    if total_messages > 500:
        return 2
    if total_messages > 100:
        return 3
    if total_messages > 20:
        return 3
    return 4


def _contact_placeholder(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]", "_", name.lower()).strip("_")
    return f"wa_{slug}"


def build_voice_profile(omar_msgs: list) -> dict:
    if not omar_msgs:
        return {}
    by_lang = defaultdict(list)
    for m in omar_msgs:
        lang = _detect_language(m["content"])
        by_lang[lang].append(m["content"])
    profiles = {}
    for lang, texts in by_lang.items():
        lengths = [len(t) for t in texts]
        emoji_counts = [len(_EMOJI_RE.findall(t)) for t in texts]
        punct = [1 for t in texts if t.endswith((".", "!", "?"))]
        caps = [1 for t in texts if t[:1].isupper()]
        profiles[lang] = {
            "avg_message_length": round(sum(lengths) / len(lengths)),
            "emoji_rate": round(sum(emoji_counts) / len(texts), 3),
            "formality_level": round((sum(punct) + sum(caps)) / (2 * len(texts)), 2),
            "message_count": len(texts),
        }
    return profiles


def extract_few_shots(messages: list, omar_name: str, contact_name: str, tier: int) -> list:
    """Extract Omar's reply turns as few-shot examples."""
    shots = []
    i = 0
    while i < len(messages):
        # Collect contact's turn
        contact_turn = []
        while i < len(messages) and messages[i]["sender"] != omar_name:
            contact_turn.append(messages[i]["content"])
            i += 1
        # Collect Omar's turn
        omar_turn = []
        while i < len(messages) and messages[i]["sender"] == omar_name:
            omar_turn.append(messages[i]["content"])
            i += 1
        if contact_turn and omar_turn:
            input_text = " ".join(contact_turn[-2:])  # last 2 contact msgs
            output_text = "\n".join(omar_turn[:3])    # first 3 Omar msgs
            lang = _detect_language(output_text)
            shots.append({
                "id": str(uuid.uuid4()),
                "language": lang,
                "relationship_tier": tier,
                "context": f"Chat with {contact_name}",
                "input": input_text[:500],
                "output": output_text[:500],
                "source": "whatsapp_export",
            })
    return shots


def upsert_voice_profile(conn, language: str, stats: dict) -> None:
    avg_len = stats.get("avg_message_length", 0)
    formality = stats.get("formality_level", 0.5)
    emoji_rate = stats.get("emoji_rate", 0.0)
    length_style = "short" if avg_len < 60 else "medium" if avg_len < 150 else "long"
    emoji_behavior = "frequent" if emoji_rate > 0.3 else "occasional" if emoji_rate > 0.05 else "rare"

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO omar_voice_profiles
                (language, avg_message_length, formality_level, emoji_behavior,
                 message_length_style, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (language) DO UPDATE SET
                avg_message_length = EXCLUDED.avg_message_length,
                formality_level    = EXCLUDED.formality_level,
                emoji_behavior     = EXCLUDED.emoji_behavior,
                message_length_style = EXCLUDED.message_length_style,
                updated_at         = NOW()
            """,
            (language, avg_len, formality, emoji_behavior, length_style),
        )
    conn.commit()


def insert_few_shots(conn, shots: list) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for s in shots:
            cur.execute(
                """
                INSERT INTO omar_few_shots
                    (id, language, relationship_tier, context, input, output, source, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (s["id"], s["language"], s["relationship_tier"],
                 s["context"], s["input"], s["output"], s["source"]),
            )
            inserted += 1
    conn.commit()
    return inserted


def upsert_contact_profile(conn, placeholder: str, name: str, tier: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO contacts (phone_number, name, relationship_tier, created_at, updated_at)
            VALUES (%s, %s, %s, NOW(), NOW())
            ON CONFLICT (phone_number) DO UPDATE SET
                name = EXCLUDED.name,
                relationship_tier = EXCLUDED.relationship_tier,
                updated_at = NOW()
            """,
            (placeholder, name, tier),
        )
        cur.execute(
            """
            INSERT INTO contact_state (contact_phone, updated_at)
            VALUES (%s, NOW())
            ON CONFLICT (contact_phone) DO NOTHING
            """,
            (placeholder,),
        )
        cur.execute(
            """
            INSERT INTO per_person_rules (contact_phone, updated_at)
            VALUES (%s, NOW())
            ON CONFLICT (contact_phone) DO NOTHING
            """,
            (placeholder,),
        )
        # Flag phone number as unknown gap
        cur.execute(
            """
            INSERT INTO contact_knowledge_gaps
                (id, contact_phone, field, priority, status, created_at)
            VALUES (%s, %s, 'phone_number', 0.9, 'pending', NOW())
            ON CONFLICT DO NOTHING
            """,
            (str(uuid.uuid4()), placeholder),
        )
    conn.commit()


def process_file(conn, path: Path, omar_name: str) -> None:
    print(f"\nParsing {path.name} ...")
    messages = parse_export(path)
    if not messages:
        print("  No messages parsed - skipping")
        return

    senders = {m["sender"] for m in messages}
    others = senders - {omar_name}
    if not others:
        print("  No other sender found - skipping")
        return

    contact_name = others.pop() if len(others) == 1 else path.stem
    placeholder = _contact_placeholder(contact_name)
    total = len(messages)
    tier = _estimate_tier(total)

    print(f"  Contact: {contact_name} -> placeholder: {placeholder}")
    print(f"  Messages: {total}, estimated tier: {tier}")

    omar_msgs = [m for m in messages if m["sender"] == omar_name]
    voice_stats = build_voice_profile(omar_msgs)

    for lang, stats in voice_stats.items():
        upsert_voice_profile(conn, lang, stats)
        print(f"  Voice profile upserted: {lang} ({stats['message_count']} msgs)")

    shots = extract_few_shots(messages, omar_name, contact_name, tier)
    n_shots = insert_few_shots(conn, shots)
    print(f"  Few-shots inserted: {n_shots}")

    upsert_contact_profile(conn, placeholder, contact_name, tier)
    print(f"  Contact profile created: {placeholder}")


def main():
    parser = argparse.ArgumentParser(description="Ingest WhatsApp exports into Ghost v2 DB")
    parser.add_argument("--omar-name", default="Omar", help="Your name as it appears in exports")
    parser.add_argument("files", nargs="+", help=".txt export files")
    args = parser.parse_args()

    conn = get_conn()
    for f in args.files:
        path = Path(f).expanduser()
        if not path.exists():
            print(f"File not found: {f}")
            continue
        process_file(conn, path, args.omar_name)
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
