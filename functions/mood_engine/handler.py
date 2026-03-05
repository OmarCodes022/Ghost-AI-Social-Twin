"""ghost_mood_engine

Computes a mood vector from contextual signals:
  - Time of day  → energy curve + patience
  - Day of week  → warmth and humor modifiers (weekends loosen things up)
  - Contact tier → warmth (close friends get more warmth)
  - Conversation velocity → energy boost when back-and-forth is rapid
"""
import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any

from models import MoodEngineRequest, MoodEngineResponse, MoodState

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def lambda_handler(event: dict, context: Any) -> dict:
    logger.info(json.dumps({"event": "mood_engine_invoked"}))

    request = MoodEngineRequest(**event)
    now = datetime.now(timezone.utc)
    hour = now.hour
    weekday = now.weekday()  # 0=Mon, 6=Sun
    tier = int(request.contact_context.get("relationship_tier", 3))
    recent_count = len(request.recent_messages)

    signals_used = [
        f"hour:{hour}",
        f"weekday:{weekday}",
        f"contact_tier:{tier}",
        f"recent_messages:{recent_count}",
    ]

    # ── Energy: sinusoidal curve peaking ~10am, lowest ~4am ──────────────────
    energy = 0.4 + 0.45 * math.cos(math.pi * (hour - 10) / 12)
    energy = _clamp(energy, 0.1, 0.95)
    if recent_count >= 5:
        energy = _clamp(energy + 0.1, 0.1, 0.95)
        signals_used.append("velocity:high")

    # ── Warmth: close contacts always get more ────────────────────────────────
    # tier 1→0.90, tier 2→0.76, tier 3→0.62, tier 4→0.48, tier 5→0.34
    warmth = 0.90 - (tier - 1) * 0.14
    warmth = _clamp(warmth, 0.2, 0.95)
    if weekday >= 5:  # Sat / Sun
        warmth = _clamp(warmth + 0.08, 0.2, 0.95)
        signals_used.append("weekend:true")

    # ── Humor: evenings and weekends unlock playfulness ───────────────────────
    if weekday >= 5 or hour >= 18:
        humor = 0.72
    elif 9 <= hour <= 17:
        humor = 0.5
    else:
        humor = 0.25

    # ── Openness: high during waking hours, low late night ───────────────────
    openness = 0.8 if 8 <= hour <= 21 else 0.3

    # ── Patience: mirrors energy ──────────────────────────────────────────────
    patience = _clamp(0.25 + 0.65 * energy, 0.2, 0.95)

    mood = MoodState(
        energy=round(energy, 2),
        warmth=round(warmth, 2),
        humor_threshold=round(humor, 2),
        openness=round(openness, 2),
        patience=round(patience, 2),
        signals={
            "hour": hour,
            "weekday": weekday,
            "tier": tier,
            "recent_count": recent_count,
        },
    )

    logger.info(
        json.dumps({
            "event": "mood_computed",
            "energy": mood.energy,
            "warmth": mood.warmth,
            "humor": mood.humor_threshold,
            "openness": mood.openness,
            "patience": mood.patience,
        })
    )

    return MoodEngineResponse(mood_state=mood, signals_used=signals_used).model_dump(mode="json")


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
