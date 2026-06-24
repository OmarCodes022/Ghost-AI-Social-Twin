#!/usr/bin/env python3
"""
Ingest Omar's structured identity interview markdown into memories.

Usage:
    ENV=dev python ingest_interview.py omar_identity.md
"""
import sys
from pathlib import Path

from ghost_ingest_utils import get_db_connection, insert_memory

CATEGORY_MAP = {
    "Life Story": "identity",
    "Values & Worldview": "identity",
    "Voice — French": "behavioral",
    "Voice — English": "behavioral",
    "Voice — Arabic": "behavioral",
    "Deep Interests & Opinions": "identity",
    "Humor Style": "behavioral",
    "Social Behavior Patterns": "behavioral",
    "Emotional Defaults": "behavioral",
    "No-Go Topics": "identity",
    "Formative People & Experiences": "identity",
    "Current Life Situation": "identity",
    "Image Management": "behavioral",
    "Current Focus & Obsessions": "identity",
    "Rules & Limits": "identity",
}

IMPORTANCE_MAP = {
    "identity": 0.9,
    "behavioral": 0.8,
}

MAX_TOKENS = 800  # rough estimate: 1 token ~= 4 chars = 3200 chars


def parse_sections(markdown: str) -> list:
    sections = []
    current_title = None
    current_lines = []
    for line in markdown.splitlines():
        if line.startswith("## "):
            if current_title:
                sections.append({"title": current_title, "content": "\n".join(current_lines).strip()})
            current_title = line[3:].strip()
            current_lines = []
        elif current_title:
            current_lines.append(line)
    if current_title:
        sections.append({"title": current_title, "content": "\n".join(current_lines).strip()})
    return sections


def chunk_section(content: str) -> list:
    if len(content) / 4 <= MAX_TOKENS:
        return [content]
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    chunks = []
    current = []
    current_len = 0
    for para in paragraphs:
        para_len = len(para) / 4
        if current_len + para_len > MAX_TOKENS and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def run(filepath: str) -> None:
    markdown = Path(filepath).read_text(encoding="utf-8")
    sections = parse_sections(markdown)
    conn = get_db_connection()
    inserted = 0
    for section in sections:
        title = section["title"]
        category = CATEGORY_MAP.get(title)
        if not category:
            print(f"WARNING: unknown section '{title}', skipping")
            continue
        importance = IMPORTANCE_MAP[category]
        for chunk in chunk_section(section["content"]):
            content = f"[{title}]\n{chunk}"
            insert_memory(conn, content, category, "english", importance)
            inserted += 1
            print(f"  inserted '{title}' ({len(chunk)} chars)")
    conn.close()
    print(f"\nDone - {inserted} memory rows inserted.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: ENV=dev python ingest_interview.py omar_identity.md")
        sys.exit(1)
    run(sys.argv[1])
