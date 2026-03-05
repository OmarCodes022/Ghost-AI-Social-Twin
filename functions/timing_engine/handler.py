"""ghost_timing_engine

Decides whether to reply immediately or queue a delayed send via SQS.

Decision matrix:
  - Tier 1 (close friend): always immediate
  - Tier 2–5: randomised delay window based on tier
  - Low mood energy (<0.3): delay window multiplied by 1.5
  - Late night (22:00–07:00) + tier >= 3: max SQS delay (900 s)
  - All delays capped at 900 s (SQS native maximum)
"""
import json
import logging
import os
import random
from datetime import datetime, timezone
from typing import Any

from db import get_cursor
from models import TimingEngineRequest, TimingEngineResponse

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# (min_seconds, max_seconds) per relationship tier
_TIER_WINDOWS: dict[int, tuple[int, int]] = {
    1: (0, 0),      # always immediate
    2: (5, 45),
    3: (30, 180),
    4: (60, 360),
    5: (120, 600),
}
_SQS_MAX = 900


def lambda_handler(event: dict, context: Any) -> dict:
    logger.info(json.dumps({"event": "timing_engine_invoked"}))

    request = TimingEngineRequest(**event)
    now = datetime.now(timezone.utc)
    hour = now.hour
    tier = _get_contact_tier(request.contact_phone)
    energy = request.mood_state.energy

    lo, hi = _TIER_WINDOWS.get(tier, (60, 300))

    # Low energy → slower replies
    if energy < 0.3:
        lo = int(lo * 1.5)
        hi = int(hi * 1.5)
        reasoning = f"tier{tier}_low_energy"
    else:
        reasoning = f"tier{tier}"

    # Late night penalty for non-close contacts
    is_late_night = hour >= 22 or hour < 7
    if is_late_night and tier >= 3:
        delay_seconds = _SQS_MAX
        reasoning = f"late_night:tier{tier}"
    elif hi == 0:
        delay_seconds = 0
    else:
        delay_seconds = random.randint(lo, hi)

    delay_seconds = min(delay_seconds, _SQS_MAX)
    reply_now = delay_seconds == 0

    logger.info(
        json.dumps({
            "event": "timing_decided",
            "reply_now": reply_now,
            "delay_seconds": delay_seconds,
            "tier": tier,
            "hour": hour,
            "energy": energy,
        })
    )

    return TimingEngineResponse(
        reply_now=reply_now,
        delay_seconds=delay_seconds,
        reasoning=reasoning,
    ).model_dump(mode="json")


def _get_contact_tier(phone_number: str) -> int:
    with get_cursor() as cur:
        cur.execute(
            "SELECT relationship_tier FROM contacts WHERE phone_number = %s",
            (phone_number,),
        )
        row = cur.fetchone()
        return int(row["relationship_tier"]) if row else 3
