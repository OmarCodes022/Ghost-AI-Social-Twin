#!/usr/bin/env python3
"""
Ingest Omar's freeform writing document into Ghost v2 memories.

Uses Claude Haiku to categorize unstructured text into known subsections,
then embeds and inserts each chunk into memories.

Usage:
    ENV=dev python ingest_freeform.py omar_freeform.md
"""
import json
import sys
from pathlib import Path

import boto3

from ghost_ingest_utils import get_db_connection, insert_memory

REGION = "eu-west-1"

IMPORTANCE_MAP = {
    "identity": 0.9,
    "behavioral": 0.8,
}

VALID_SUBSECTIONS = [
    "Life Story", "Values & Worldview", "Voice — French", "Voice — English",
    "Voice — Arabic", "Deep Interests & Opinions", "Humor Style",
    "Social Behavior Patterns", "Emotional Defaults", "No-Go Topics",
    "Formative People & Experiences", "Current Life Situation",
    "Image Management", "Current Focus & Obsessions", "Rules & Limits",
]

CATEGORY_MAP = {
    "Life Story": "identity", "Values & Worldview": "identity",
    "Voice — French": "behavioral", "Voice — English": "behavioral",
    "Voice — Arabic": "behavioral", "Deep Interests & Opinions": "identity",
    "Humor Style": "behavioral", "Social Behavior Patterns": "behavioral",
    "Emotional Defaults": "behavioral", "No-Go Topics": "identity",
    "Formative People & Experiences": "identity", "Current Life Situation": "identity",
    "Image Management": "behavioral", "Current Focus & Obsessions": "identity",
    "Rules & Limits": "identity",
}


def _get_api_key() -> str:
    import os
    ssm = boto3.client("ssm", region_name=REGION)
    return ssm.get_parameter(
        Name=f"/ghost/{os.environ['ENV']}/anthropic/api_key", WithDecryption=True
    )["Parameter"]["Value"]


def categorize(text: str) -> list:
    import anthropic
    client = anthropic.Anthropic(api_key=_get_api_key())
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""Split this freeform document into meaningful chunks and categorize each against these subsections:
{", ".join(VALID_SUBSECTIONS)}

Return ONLY valid JSON, no preamble:
[{{"content": "chunk text", "subsection": "subsection name", "category": "identity or behavioral"}}]

Document:
{text}""",
        }],
    )
    return json.loads(resp.content[0].text)


def run(filepath: str) -> None:
    text = Path(filepath).read_text(encoding="utf-8")
    print(f"Categorizing {len(text)} chars with Claude Haiku ...")
    chunks = categorize(text)
    print(f"Got {len(chunks)} chunks")

    conn = get_db_connection()
    inserted = 0
    for chunk in chunks:
        subsection = chunk.get("subsection", "")
        category = chunk.get("category") or CATEGORY_MAP.get(subsection, "identity")
        content = f"[{subsection}]\n{chunk['content']}" if subsection else chunk["content"]
        importance = IMPORTANCE_MAP.get(category, 0.8)
        insert_memory(conn, content, category, "english", importance)
        inserted += 1
        print(f"  inserted [{subsection}] ({len(chunk['content'])} chars)")

    conn.close()
    print(f"\nDone - {inserted} memory rows inserted.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: ENV=dev python ingest_freeform.py omar_freeform.md")
        sys.exit(1)
    run(sys.argv[1])
