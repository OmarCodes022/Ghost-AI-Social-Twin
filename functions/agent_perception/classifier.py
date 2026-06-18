import json
import os
import boto3
from .models import Classification, MsgType, Urgency

_MODEL = "anthropic.claude-haiku-4-5"
_bedrock = None

_SYSTEM = """\
You are a message classifier for a WhatsApp AI agent.
Classify the incoming message and return ONLY valid JSON — no explanation, no markdown.

JSON schema:
{
  "msg_type": "question|statement|greeting|farewell|media|voice_note|other",
  "urgency": "high|medium|low",
  "sentiment": "positive|neutral|negative",
  "needs_response": true|false,
  "escalate": false,
  "notes": "one short sentence or null"
}

escalate = true only if the message requires the real Omar urgently (emergency, crisis, or something Ghost absolutely cannot handle).
needs_response = false for spam, receipts, or purely informational messages with no social expectation of reply.\
"""


def _client():
    global _bedrock
    if not _bedrock:
        _bedrock = boto3.client("bedrock-runtime", region_name=os.environ["AWS_REGION"])
    return _bedrock


def classify(content: str, contact_name: str) -> Classification:
    prompt = f"Contact: {contact_name}\nMessage: {content}"

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 256,
        "system": _SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    })

    resp = _client().invoke_model(modelId=_MODEL, body=body)
    raw = json.loads(resp["body"].read())
    data = json.loads(raw["content"][0]["text"])

    return Classification(
        msg_type=MsgType(data["msg_type"]),
        urgency=Urgency(data["urgency"]),
        sentiment=data["sentiment"],
        needs_response=data["needs_response"],
        escalate=data.get("escalate", False),
        notes=data.get("notes"),
    )
