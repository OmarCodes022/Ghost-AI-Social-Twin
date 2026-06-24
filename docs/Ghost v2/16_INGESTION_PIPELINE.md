# 16 — Ingestion Pipeline

## Purpose

This document specifies the implementation of every ingestion script in Ghost v2 — the code-level bridge between raw source content (interview markdown, WhatsApp exports) and the database tables those sources populate. The 16-document architecture set defines *what* needs to exist in the DB and *why*; this document defines *how* it gets there.

Three scripts are specified here, in the order they should be built:

1. **`ingest_interview.py`** — Layer 1 of `11_ONBOARDING_OMAR.md`: reads the structured interview markdown, chunks by section, embeds via Voyage-3, inserts into `memories`
2. **`ingest_whatsapp.py`** — Layer 2 of `11_ONBOARDING_OMAR.md` and all of `12_ONBOARDING_CONTACTS.md`: reads WhatsApp export files, extracts Omar's voice per language + contact starter profiles simultaneously
3. **`ingest_freeform.py`** — Layer 3 of `11_ONBOARDING_OMAR.md`: reads Omar's freeform writing document, categorizes sections, inserts into `memories`

All three share the same embedding logic and DB connection setup — implement that as a shared module (`ghost_ingest_utils.py`) rather than duplicating it across scripts.

---

## Shared Setup — `ghost_ingest_utils.py`

### DB Connection

```python
import psycopg2
from psycopg2.extras import RealDictCursor
import boto3
import os

def get_db_connection():
    ssm = boto3.client('ssm', region_name='eu-west-1')
    conn_string = ssm.get_parameter(
        Name=f"/ghost/{os.environ['ENV']}/db/connection_string",
        WithDecryption=True
    )['Parameter']['Value']
    return psycopg2.connect(conn_string, cursor_factory=RealDictCursor)
```

`ENV` is always set as an environment variable (`dev` or `prod`) — never hardcoded. This is the same SSM path structure defined in `13_INFRASTRUCTURE.md`.

### Embedding via Voyage-3

```python
import anthropic

def embed(text: str) -> list[float]:
    client = anthropic.Anthropic()
    response = client.embeddings.create(
        model="voyage-3",
        input=[text]
    )
    return response.embeddings[0].embedding
```

**Critical constraints:**
- Model is always `voyage-3` — never `voyage-3-lite`, never Titan, never anything else. This is the fixed multilingual model chosen in `03_MEMORY_SYSTEM.md`. One model, one dimensionality (1024), no exceptions.
- Output is always `vector(1024)` — matches the `memories.embedding` column exactly. If this ever produces a different length, something is wrong with the model string, not the column.
- Voyage-3 is called via the Anthropic SDK, not via Bedrock — use the Anthropic API key from SSM (`/ghost/{env}/anthropic/api_key`), not the Bedrock region config.

### Memory Insert

```python
import uuid
from datetime import datetime

def insert_memory(conn, content: str, category: str, language: str,
                  importance: float, contact_phone: str = None,
                  source_conversation: str = None):
    embedding = embed(content)
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO memories (
                id, contact_phone, category, content, language,
                embedding, importance, created_at, created_by, source_conversation
            ) VALUES (%s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s)
        """, (
            str(uuid.uuid4()),
            contact_phone,        # NULL for Omar's identity memories
            category,
            content,
            language,
            embedding,
            importance,
            datetime.utcnow(),
            'onboarding',
            source_conversation   # NULL for onboarding
        ))
    conn.commit()
```

---

## Script 1 — `ingest_interview.py`

### Input

The structured markdown file produced by the Layer 1 interview. Expected format:

```markdown
# Omar — Identity Source Document

## Life Story
[content]

## Values & Worldview
[content]

## Voice — French
[content]

## Voice — English
[content]

## Voice — Arabic
[content]

## Deep Interests & Opinions
[content]

## Humor Style
[content]

## Social Behavior Patterns
[content]

## Emotional Defaults
[content]

## No-Go Topics
[content]

## Formative People & Experiences
[content]

## Current Life Situation
[content]

## Image Management
[content]

## Current Focus & Obsessions
[content]

## Rules & Limits
[content]
```

### Chunking Strategy

Each `##` section is one chunk — do not split sections further, do not merge sections together. The section boundaries are semantically meaningful (they map directly to the 10 categories in `01_INFORMATION_ARCHITECTURE.md`), and RAG retrieval works best when chunk boundaries match the natural semantic units of the content.

Exception: if any single section exceeds 800 tokens, split it at paragraph boundaries, not mid-paragraph. Each sub-chunk should still be tagged with the same section name as its parent.

### Category Mapping

| Section header | `memories.category` |
|---|---|
| Life Story | `identity` |
| Values & Worldview | `identity` |
| Voice — French | `behavioral` |
| Voice — English | `behavioral` |
| Voice — Arabic | `behavioral` |
| Deep Interests & Opinions | `identity` |
| Humor Style | `behavioral` |
| Social Behavior Patterns | `behavioral` |
| Emotional Defaults | `behavioral` |
| No-Go Topics | `identity` |
| Formative People & Experiences | `identity` |
| Current Life Situation | `identity` |
| Image Management | `behavioral` |
| Current Focus & Obsessions | `identity` |
| Rules & Limits | `identity` |

### Language Field

All chunks from the interview are written in English (the interview is conducted in English). Set `language = 'english'` for all rows. This does not affect retrieval — Voyage-3 is multilingual and will correctly surface these chunks when Ghost queries in French or Arabic.

### Importance Scoring

Static defaults per category, not computed dynamically — this is onboarding content, importance is set manually:

| Category | Default importance |
|---|---|
| `identity` | 0.9 |
| `behavioral` | 0.8 |

These can be manually adjusted per chunk after the initial insert if specific chunks are judged more or less critical.

### Fixed Fields

```python
contact_phone = None       # Omar's identity memories have no contact
created_by = 'onboarding'
source_conversation = None
```

### Implementation

```python
import re
import sys
from ghost_ingest_utils import get_db_connection, insert_memory

CATEGORY_MAP = {
    'Life Story': 'identity',
    'Values & Worldview': 'identity',
    'Voice — French': 'behavioral',
    'Voice — English': 'behavioral',
    'Voice — Arabic': 'behavioral',
    'Deep Interests & Opinions': 'identity',
    'Humor Style': 'behavioral',
    'Social Behavior Patterns': 'behavioral',
    'Emotional Defaults': 'behavioral',
    'No-Go Topics': 'identity',
    'Formative People & Experiences': 'identity',
    'Current Life Situation': 'identity',
    'Image Management': 'behavioral',
    'Current Focus & Obsessions': 'identity',
    'Rules & Limits': 'identity',
}

IMPORTANCE_MAP = {
    'identity': 0.9,
    'behavioral': 0.8,
}

def parse_sections(markdown: str) -> list[dict]:
    sections = []
    current_title = None
    current_lines = []
    for line in markdown.splitlines():
        if line.startswith('## '):
            if current_title:
                sections.append({
                    'title': current_title,
                    'content': '\n'.join(current_lines).strip()
                })
            current_title = line[3:].strip()
            current_lines = []
        elif current_title:
            current_lines.append(line)
    if current_title:
        sections.append({
            'title': current_title,
            'content': '\n'.join(current_lines).strip()
        })
    return sections

def chunk_section(title: str, content: str, max_tokens: int = 800) -> list[str]:
    # Rough token estimate: 1 token ≈ 4 chars
    if len(content) / 4 <= max_tokens:
        return [content]
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    chunks = []
    current = []
    current_len = 0
    for para in paragraphs:
        para_len = len(para) / 4
        if current_len + para_len > max_tokens and current:
            chunks.append('\n\n'.join(current))
            current = [para]
            current_len = para_len
        else:
            current.append(para)
            current_len += para_len
    if current:
        chunks.append('\n\n'.join(current))
    return chunks

def run(filepath: str):
    with open(filepath, 'r') as f:
        markdown = f.read()
    sections = parse_sections(markdown)
    conn = get_db_connection()
    inserted = 0
    for section in sections:
        title = section['title']
        category = CATEGORY_MAP.get(title)
        if not category:
            print(f"WARNING: unknown section '{title}', skipping")
            continue
        importance = IMPORTANCE_MAP[category]
        chunks = chunk_section(title, section['content'])
        for chunk in chunks:
            content = f"[{title}]\n{chunk}"  # prepend section label to each chunk
            insert_memory(conn, content, category, 'english', importance)
            inserted += 1
            print(f"Inserted chunk from '{title}' ({len(chunk)} chars)")
    conn.close()
    print(f"\nDone — {inserted} memory rows inserted.")

if __name__ == '__main__':
    run(sys.argv[1])
```

**Run with:**
```bash
ENV=dev python ingest_interview.py omar_identity.md
```

---

## Script 2 — `ingest_whatsapp.py`

### Purpose

This script processes one or more WhatsApp export `.txt` files and produces two categories of output simultaneously (per `11_ONBOARDING_OMAR.md` Layer 2 and `12_ONBOARDING_CONTACTS.md`):

1. **Omar's voice** — per-language voice profiles (`omar_voice_profiles`) and real few-shot examples (`omar_few_shots`)
2. **Contact starter profiles** — one row per contact in `contacts`, `contact_state`, `per_person_rules`, `contact_knowledge_gaps`, plus any facts into `memories` and dates into `life_events`

### Input Format

WhatsApp exports two formats depending on device:

**iOS:**
```
[DD/MM/YYYY, HH:MM:SS] Name: message content
```

**Android:**
```
DD/MM/YYYY, HH:MM - Name: message content
```

The script must handle both. Multi-line messages (where continuation lines have no timestamp prefix) should be joined to their parent message.

### Core Logic

```python
import re
from collections import defaultdict

# iOS pattern
IOS_PATTERN = re.compile(
    r'\[(\d{2}/\d{2}/\d{4}), (\d{2}:\d{2}:\d{2})\] ([^:]+): (.+)'
)
# Android pattern
ANDROID_PATTERN = re.compile(
    r'(\d{2}/\d{2}/\d{4}), (\d{2}:\d{2}) - ([^:]+): (.+)'
)

def parse_export(filepath: str) -> list[dict]:
    messages = []
    current = None
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip()
            m = IOS_PATTERN.match(line) or ANDROID_PATTERN.match(line)
            if m:
                if current:
                    messages.append(current)
                date, time, sender, content = m.group(1), m.group(2), m.group(3), m.group(4)
                current = {'date': date, 'time': time, 'sender': sender.strip(), 'content': content}
            elif current:
                current['content'] += '\n' + line  # multi-line continuation
    if current:
        messages.append(current)
    return messages
```

### Omar's Name Detection

The script needs to know which sender name corresponds to Omar in each export file (name varies by contact's saved name for him). Accept as a CLI argument:

```bash
ENV=dev python ingest_whatsapp.py --omar-name "Omar" export1.txt export2.txt
```

### Voice Extraction

For each export file, separate Omar's messages from the contact's messages. Then:

1. Detect language per message using `langdetect` or equivalent — group Omar's messages by detected language
2. Per language, compute:
   - Average message length (chars)
   - Emoji usage rate (emojis per message)
   - Average messages per turn (burst tendency)
   - Formality indicators (presence of punctuation, capitalization patterns)
   - Common slang/expressions (high-frequency informal tokens not in standard dictionary)
3. Write one row per language to `omar_voice_profiles` (upsert — if a row for this language exists, update rather than duplicate)
4. Extract few-shot examples: for each of Omar's reply turns (Omar message(s) following contact message(s)), store the contact's last message as `input` and Omar's reply as `output`, tagged with detected language and estimated relationship tier

### Relationship Tier Estimation

Rough heuristic from message frequency and tone — not expected to be perfect, Agent 3 will refine over time:

| Messages exchanged | Starting tier estimate |
|---|---|
| > 500 | 1 or 2 |
| 100–500 | 2 or 3 |
| 20–100 | 3 |
| < 20 | 4 or 5 |

### Contact Profile Output

For each non-Omar contact in the exports:

- Insert into `contacts` (phone number unknown from export — use a placeholder key derived from name until WhatsApp Business API provides the real E.164 number on first contact)
- Insert conservative defaults into `per_person_rules` (per `12_ONBOARDING_CONTACTS.md` Layer 2 defaults)
- Extract any facts mentioned in the conversation → `memories` with `contact_phone` set, `category='fact'`, embedded via Voyage-3
- Extract any dates or events mentioned → `life_events`
- Flag everything that could not be determined → `contact_knowledge_gaps`

### Known Limitation

WhatsApp exports do not include phone numbers — only display names. The contact rows written here will have placeholder identifiers until the contact actually messages Ghost through the WhatsApp Business API, at which point the webhook receiver can match by name or the record can be manually linked. This is a known gap, not a blocker.

---

## Script 3 — `ingest_freeform.py`

### Purpose

Processes Omar's freeform writing document (Layer 3 of `11_ONBOARDING_OMAR.md`) — unstructured text Omar writes himself, in whatever order and structure he chooses. Unlike the interview markdown (which has predefined section headers), this document may have Omar's own headers, no headers, or mixed structure.

### Approach

Since the structure is unpredictable, use an LLM pass (Claude Haiku, cheap) to:
1. Read the full freeform document
2. Categorize each paragraph/section against the known category-1 subsections from `01_INFORMATION_ARCHITECTURE.md`
3. Return structured JSON: `[{"content": "...", "category": "identity|behavioral", "subsection": "Life Story|Values & Worldview|..."}]`
4. Insert each item into `memories` exactly as `ingest_interview.py` does

```python
import anthropic
import json

def categorize_freeform(text: str) -> list[dict]:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""You are processing a freeform document written by Omar about himself.
            
Split it into meaningful chunks and categorize each chunk against these subsections:
Life Story, Values & Worldview, Voice — French, Voice — English, Voice — Arabic,
Deep Interests & Opinions, Humor Style, Social Behavior Patterns, Emotional Defaults,
No-Go Topics, Formative People & Experiences, Current Life Situation, Image Management,
Current Focus & Obsessions, Rules & Limits.

Return ONLY valid JSON, no preamble:
[{{"content": "chunk text", "subsection": "subsection name", "category": "identity or behavioral"}}]

Document:
{text}"""
        }]
    )
    return json.loads(response.content[0].text)
```

---

## Running Order

```bash
# Phase 0 — DB must exist first
# Run schema migration from 09_DB_SCHEMA.md before any of these

# Phase 1a — Interview (do this first, it's the most important)
ENV=dev python ingest_interview.py omar_identity.md

# Phase 1b — WhatsApp exports (run against as many export files as available)
ENV=dev python ingest_whatsapp.py --omar-name "Omar" *.txt

# Phase 1c — Freeform writing (run whenever Omar finishes writing it)
ENV=dev python ingest_freeform.py omar_freeform.md
```

All three scripts are idempotent in the sense that re-running them produces duplicate rows rather than errors — but duplicates in `memories` will degrade RAG quality. Add a `source_file` column or hash check if re-runs become necessary.

---

## What the IDE Agent Needs to Run These

1. This document (`16_INGESTION_PIPELINE.md`)
2. `09_DB_SCHEMA.md` — for the exact table schemas
3. `11_ONBOARDING_OMAR.md` — for context on what the interview output looks like
4. `12_ONBOARDING_CONTACTS.md` — for contact defaults logic
5. The actual source files: `omar_identity.md` (interview output), WhatsApp `.txt` exports, `omar_freeform.md`
6. AWS credentials + `ENV=dev` set in environment
7. `pip install psycopg2-binary anthropic langdetect`

No other context needed — everything implementation-relevant is in these four documents.
