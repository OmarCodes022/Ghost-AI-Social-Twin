from datetime import datetime

# Hard limits for Ghost-initiated outreach only - never applied to replies
SLEEP_START_HOUR = 23   # 11 PM UTC
SLEEP_END_HOUR = 8      # 8 AM UTC
MIN_HEARTBEAT_SPACING_HOURS = 0.5  # 30 minutes between heartbeat actions per contact


def is_outreach_allowed(contact: dict, now: datetime) -> bool:
    """
    Hard guardrail: returns False if Ghost must not initiate outreach right now.
    Does NOT apply to replies - only Ghost-initiated heartbeat contacts.
    """
    h = now.hour
    if h >= SLEEP_START_HOUR or h < SLEEP_END_HOUR:
        return False

    last_hb = contact.get("last_heartbeat_at")
    if last_hb:
        hours_since = (now - last_hb).total_seconds() / 3600
        if hours_since < MIN_HEARTBEAT_SPACING_HOURS:
            return False

    return True
