import json
import os
import boto3
from models import Classification

_MODEL = "anthropic.claude-haiku-4-5"
_bedrock = None

_SYSTEM = """\
You are a perception layer for an AI that impersonates a person over WhatsApp.
Analyse the incoming message and return ONLY valid JSON — no explanation, no markdown.

JSON schema:
{
  "language": "french|english|arabic",
  "emotion": "<one word describing the contact's emotional tone, e.g. dry, worried, excited, flat, warm, playful, tense>",
  "intent": "<one word or short phrase, e.g. checking_in, venting, question, greeting, farewell, sharing_news, asking_favour>",
  "urgency": "high|medium|low",
  "attitude_shift": <float -1.0 to +1.0; how this message shifts the contact's attitude toward Ghost; 0.0 = neutral>,
  "sensitivity_flags": [<list of strings; only include if truly sensitive: "suicidal", "crisis", "threat", "legal", "medical_emergency", "grief">],
  "topic_summary": "<one short sentence: what is this message actually about>"
}

attitude_shift guidelines:
- positive shift (+0.1 to +1.0): warm, appreciative, playful, excited, grateful
- neutral (0.0): routine, informational, ambiguous
- negative shift (-0.1 to -1.0): cold, annoyed, passive-aggressive, hurt, confrontational

sensitivity_flags: ONLY list flags for genuine emergencies or highly sensitive situations.
Most messages should have an empty list [].
"""


def _client():
    global _bedrock
    if not _bedrock:
        _bedrock = boto3.client("bedrock-runtime", region_name=os.environ["AWS_REGION"])
    return _bedrock


def classify(content: str, contact_name: str) -> Classification:
    prompt = f"Contact name: {contact_name}\nMessage: {content}"

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 300,
        "system": _SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    })

    resp = _client().invoke_model(modelId=_MODEL, body=body)
    raw = json.loads(resp["body"].read())
    data = json.loads(raw["content"][0]["text"])

    return Classification(
        language=data["language"],
        emotion=data["emotion"],
        intent=data["intent"],
        urgency=data["urgency"],
        attitude_shift=float(data["attitude_shift"]),
        sensitivity_flags=data.get("sensitivity_flags", []),
        topic_summary=data["topic_summary"],
    )
