from datetime import datetime, timezone


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

# Tunable - adjust post-launch without code changes by extracting to SSM config if needed
WEIGHTS = {
    "recency": 0.25,
    "attitude_trend": 0.20,
    "unanswered": 0.30,
    "life_event": 0.10,
    "intention": 0.10,
    "time_of_day": 0.05,
}

SCORE_THRESHOLD = 0.65


def _recency(contact: dict, now: datetime) -> float:
    """How overdue is this contact vs their baseline communication frequency?"""
    baseline = contact.get("baseline_frequency")  # in days
    last_at = contact.get("last_interaction_at")
    if not baseline or baseline <= 0 or not last_at:
        return 0.0
    elapsed_days = (now - _utc(last_at)).total_seconds() / 86400
    ratio = elapsed_days / baseline
    return min(1.0, max(0.0, ratio - 1.0))  # 0 until overdue, then climbs


def _attitude_trend(contact: dict) -> float:
    trend = contact.get("attitude_trend", "stable")
    if trend == "declining":
        return 1.0
    if trend == "stable":
        return 0.3
    return 0.0  # improving - no urgency


def _unanswered(contact: dict, now: datetime) -> float:
    if not contact.get("unanswered_message_flag"):
        return 0.0
    since = contact.get("unanswered_since")
    if not since:
        return 0.5
    hours = (now - _utc(since)).total_seconds() / 3600
    return min(1.0, 0.5 + hours / 48.0)  # grows from 0.5 to 1.0 over 48 hours


def _life_event(contact: dict, now: datetime) -> float:
    best = 0.0
    for ev in contact.get("life_events", []):
        d = ev.get("event_date")
        if not d:
            continue
        event_dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        hours = (event_dt - now).total_seconds() / 3600
        if 0 <= hours <= 24:
            best = max(best, 1.0)
        elif 24 < hours <= 72:
            best = max(best, 0.6)
        elif 72 < hours <= 168:
            best = max(best, 0.3)
    return best


def _intention(contact: dict) -> float:
    return min(1.0, len(contact.get("ghost_intentions", [])) * 0.5)


def _time_of_day(now: datetime) -> float:
    h = now.hour
    if 9 <= h < 12 or 14 <= h < 19:
        return 1.0
    if 12 <= h < 14 or 19 <= h < 22:
        return 0.7
    return 0.0


def compute_pulse_score(contact: dict, ghost_state: dict, now: datetime) -> float:
    """
    Weighted score [0, 1] representing how much this contact warrants Ghost's attention.
    Scaled by social_battery so Ghost naturally quiets down when drained.
    """
    battery = ghost_state.get("social_battery", 0.7)
    components = {
        "recency": _recency(contact, now),
        "attitude_trend": _attitude_trend(contact),
        "unanswered": _unanswered(contact, now),
        "life_event": _life_event(contact, now),
        "intention": _intention(contact),
        "time_of_day": _time_of_day(now),
    }
    raw = sum(WEIGHTS[k] * v for k, v in components.items())
    return round(raw * battery, 4)
