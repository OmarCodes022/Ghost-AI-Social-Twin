"""ghost_timing_engine  (stub)

Decides whether to reply immediately or queue a delayed send via SQS.
Phase 2 will consider conversation arc state, time-of-day, mood, and
contact relationship tier to simulate natural reply timing.
For now: always reply immediately.
"""
import json
import logging
import os
from typing import Any

from models import TimingEngineRequest, TimingEngineResponse

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


def lambda_handler(event: dict, context: Any) -> dict:
    logger.info(json.dumps({"event": "timing_engine_invoked"}))

    request = TimingEngineRequest(**event)

    # Stub: always reply now, no delay.
    response = TimingEngineResponse(
        reply_now=True,
        delay_seconds=0,
        reasoning="stub_immediate",
    )

    return response.model_dump(mode="json")
