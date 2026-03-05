"""ghost_mood_engine  (stub)

Computes a mood vector from context signals. Phase 2 will use recent message
history, time-of-day, interaction frequency, and a Claude call to infer mood.
For now returns a neutral baseline mood.
"""
import json
import logging
import os
from typing import Any

from models import MoodEngineRequest, MoodEngineResponse, MoodState

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def lambda_handler(event: dict, context: Any) -> dict:
    logger.info(json.dumps({"event": "mood_engine_invoked"}))

    request = MoodEngineRequest(**event)

    # Stub: neutral mood across all axes.
    mood = MoodState()
    response = MoodEngineResponse(mood_state=mood, signals_used=["stub_neutral"])

    return response.model_dump(mode="json")
