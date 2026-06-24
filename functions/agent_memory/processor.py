import json
import os

import boto3

_bedrock = None
_voyage_client = None

MODEL_ID = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"


def _get_bedrock():
    global _bedrock
    if not _bedrock:
        _bedrock = boto3.client("bedrock-runtime", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
    return _bedrock


def _get_voyage():
    global _voyage_client
    if not _voyage_client:
        import voyageai
        ssm = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
        key = ssm.get_parameter(
            Name=f"/ghost/{os.environ['ENV']}/voyage/api_key", WithDecryption=True
        )["Parameter"]["Value"]
        _voyage_client = voyageai.Client(api_key=key)
    return _voyage_client


def embed(text: str) -> list:
    result = _get_voyage().embed([text], model="voyage-3")
    return result.embeddings[0]


def _build_prompt(conversation: dict, messages: list, contact: dict, contact_state: dict) -> str:
    contact_name = contact.get("name", "Unknown")
    tier = contact.get("relationship_tier", 3)
    current_attitude = contact_state.get("current_attitude_score", 0.0)

    history = "\n".join(
        f"[{m['role'].upper()}]: {m['content']}"
        for m in messages
    )

    return f"""You are analyzing a closed conversation between Ghost (an AI) and {contact_name} (relationship tier {tier}/5, 1=closest).

Current attitude score before this conversation: {current_attitude:.2f} (range -1.0 to 1.0)

Full conversation:
{history}

Analyze this conversation and return ONLY valid JSON with this exact structure:
{{
    "attitude_shift": <float -1.0 to 1.0, net change in attitude from this conversation>,
    "attitude_trend": <"improving" | "stable" | "declining">,
    "attitude_trend_duration": <int, how many consecutive conversations in this trend direction>,
    "quality_score": <float 0.0 to 1.0, overall conversation quality>,
    "emotional_tone": <string, e.g. "warm", "tense", "playful", "distant", "supportive">,
    "summary": <string, 1-2 sentence summary of the conversation>,
    "unresolved_threads": [<string, topic or question left open>],
    "new_facts": [
        {{"content": <string>, "category": <"fact"|"emotional"|"pattern"|"observation">, "importance": <float 0.0-1.0>}}
    ],
    "knowledge_gap_resolutions": [
        {{"field": <string, e.g. "city", "job", "relationship_status">}}
    ]
}}

Rules:
- attitude_shift: positive = contact became warmer/more engaged, negative = colder/more distant
- new_facts: only include genuinely new, memorable information about the contact - not obvious or trivial things
- knowledge_gap_resolutions: only include fields that were explicitly revealed in the conversation
- unresolved_threads: topics, questions, or plans mentioned but not concluded
- Return ONLY the JSON object, no explanation"""


def extract_signals(conversation: dict, messages: list, contact: dict, contact_state: dict) -> dict:
    prompt = _build_prompt(conversation, messages, contact, contact_state)
    bedrock = _get_bedrock()

    resp = bedrock.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        }),
        contentType="application/json",
        accept="application/json",
    )
    text = json.loads(resp["body"].read())["content"][0]["text"].strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    return json.loads(text)
