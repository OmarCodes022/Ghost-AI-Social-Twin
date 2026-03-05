"""ghost_escalation_detector

Classifies inbound messages to determine whether a human should review the
proposed reply before it's sent.

Uses Claude with a strict JSON output schema. Escalation triggers:
- Expressions of distress, crisis, or emergency
- Requests that require real-world action (money, meetings, urgent logistics)
- Sensitive personal topics (health, family emergencies, relationship crises)
- Ambiguous messages where getting the reply wrong could cause real harm
- Strong negative emotion (anger, grief, distress)
"""
import json
import logging
import os
from typing import Any

import anthropic

from models import EscalationDetectorRequest, EscalationDetectorResponse
from ssm import get_parameter

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

_anthropic_client: anthropic.Anthropic | None = None


def _get_anthropic_client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        env = os.environ.get("ENV", "dev")
        api_key = get_parameter(f"/ghost/{env}/anthropic/api_key")
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
    return _anthropic_client


# ─── Entry point ──────────────────────────────────────────────────────────────

def lambda_handler(event: dict, context: Any) -> dict:
    logger.info(json.dumps({"event": "escalation_detector_invoked"}))

    request = EscalationDetectorRequest(**event)

    result = _classify_message(request.message_content)

    logger.info(
        json.dumps({
            "event": "escalation_classified",
            "is_escalation": result.is_escalation,
            "confidence": result.confidence,
            "reason": result.reason,
        })
    )

    return result.model_dump(mode="json")


# ─── Classification ────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a message classifier for an AI social agent. Your job is to decide
whether an inbound WhatsApp message requires a human to review the AI's proposed
reply before it is sent.

Escalate (is_escalation=true) when the message involves:
- Expressions of distress, emotional crisis, or emergency
- Requests for real-world help (money, physical meetings, urgent logistics)
- Sensitive topics where a wrong reply could cause real harm (health crisis,
  family emergency, relationship breakdown, grief)
- Strong negative emotions directed at the user (anger, accusation, hurt)
- Anything that sounds like a test of whether this is a real person
- Explicit questions like "are you a bot?" or "is this automated?"

Do NOT escalate for:
- Normal casual conversation
- Questions that have clear factual answers
- Light emotional content (excitement, mild frustration, everyday stress)
- Compliments or small talk

Respond with valid JSON only, no other text:
{"is_escalation": <bool>, "reason": "<brief reason or null>", "confidence": <0.0-1.0>}
"""


def _classify_message(message: str) -> EscalationDetectorResponse:
    client = _get_anthropic_client()

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=128,
        system=_SYSTEM_PROMPT,
        messages=[
            {"role": "user", "content": f"Message to classify:\n{message}"}
        ],
    )

    raw = response.content[0].text.strip()

    try:
        data = json.loads(raw)
        return EscalationDetectorResponse(
            is_escalation=bool(data.get("is_escalation", False)),
            reason=data.get("reason") or None,
            confidence=float(data.get("confidence", 0.0)),
        )
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.warning(
            json.dumps({
                "event": "escalation_parse_failed",
                "raw": raw,
                "error": str(exc),
            })
        )
        # Safe default: don't escalate if we can't parse
        return EscalationDetectorResponse(is_escalation=False, confidence=0.0)
