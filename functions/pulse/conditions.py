from datetime import datetime, timezone


def evaluate_condition(condition: dict, ctx: dict, now: datetime) -> bool:
    """
    Evaluate one structured condition against current state. Pure logic, no LLM.

    ctx keys:
      created_at            datetime - when the defer/conversation was created
      ghost_state           dict     - mood, social_battery, emotional_load
      contact               dict     - full contact state row
      messages_since_condition int   - contact messages received since created_at
      life_events           list     - upcoming life events for this contact
      ghost_intentions      list     - active ghost_intentions for this contact
    """
    ctype = condition.get("type")

    if ctype == "time_elapsed":
        elapsed = (now - ctx["created_at"]).total_seconds()
        return elapsed >= condition["minutes"] * 60

    elif ctype == "time_of_day":
        h = now.hour
        return condition.get("after_hour", 0) <= h < condition.get("before_hour", 24)

    elif ctype == "day_of_week":
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        return days[now.weekday()] == condition["day"].lower()

    elif ctype == "new_message_received":
        contact = ctx["contact"]
        last_at = contact.get("last_interaction_at")
        return (
            last_at is not None
            and contact.get("last_interaction_role") == "contact"
            and last_at > ctx["created_at"]
        )

    elif ctype == "no_message_received":
        last_at = ctx["contact"].get("last_interaction_at")
        if not last_at:
            return True
        return (now - last_at).total_seconds() >= condition.get("hours", 24) * 3600

    elif ctype == "message_count":
        return ctx.get("messages_since_condition", 0) >= condition.get("count", 1)

    elif ctype == "mood_above":
        return ctx["ghost_state"].get("social_battery", 0.7) >= condition["threshold"]

    elif ctype == "mood_below":
        return ctx["ghost_state"].get("social_battery", 0.7) <= condition["threshold"]

    elif ctype == "attitude_shift":
        trend = ctx["contact"].get("attitude_trend", "stable")
        direction = condition.get("direction", "either")
        if direction == "positive":
            return trend == "improving"
        if direction == "negative":
            return trend == "declining"
        return trend in ("improving", "declining")

    elif ctype == "intention_met":
        intention_id = condition.get("intention_id")
        for intent in ctx.get("ghost_intentions", []):
            if str(intent["id"]) == intention_id:
                return intent.get("status") == "completed"
        return False

    elif ctype == "life_event_passed":
        event_id = condition.get("event_id")
        for ev in ctx.get("life_events", []):
            if str(ev["id"]) == event_id:
                d = ev["event_date"]
                event_dt = datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=timezone.utc)
                return now > event_dt
        return False

    elif ctype == "life_event_approaching":
        event_id = condition.get("event_id")
        hours_before = condition.get("hours_before", 24)
        for ev in ctx.get("life_events", []):
            if str(ev["id"]) == event_id:
                d = ev["event_date"]
                event_dt = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
                hours_to = (event_dt - now).total_seconds() / 3600
                return 0 <= hours_to <= hours_before
        return False

    elif ctype == "multiple":
        operator = condition.get("operator", "OR").upper()
        results = [evaluate_condition(c, ctx, now) for c in condition.get("conditions", [])]
        return all(results) if operator == "AND" else any(results)

    return False
