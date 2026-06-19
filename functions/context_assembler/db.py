import os
import boto3
import psycopg2
import psycopg2.extras

from models import GhostState, Contact, ContactState, PerPersonRules, Message, LifeEvent, FewShot

_conn = None

HISTORY_LIMIT = 30
LIFE_EVENTS_LIMIT = 10
FEW_SHOTS_LIMIT = 6


def _get_conn():
    global _conn
    if _conn and not _conn.closed:
        try:
            _conn.cursor().execute("SELECT 1")
            return _conn
        except Exception:
            pass

    ssm = boto3.client("ssm", region_name=os.environ["AWS_REGION"])
    url = ssm.get_parameter(
        Name=f"/ghost/{os.environ['ENV']}/db/connection_string",
        WithDecryption=True,
    )["Parameter"]["Value"]

    _conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    _conn.autocommit = True
    return _conn


def fetch_ghost_state() -> GhostState:
    with _get_conn().cursor() as cur:
        cur.execute(
            "SELECT mood, social_battery, emotional_load, current_focus, "
            "whats_on_mind, period_description FROM ghost_state WHERE id = 1"
        )
        row = cur.fetchone()
    return GhostState(
        mood=row["mood"],
        social_battery=row["social_battery"],
        emotional_load=row["emotional_load"],
        current_focus=row["current_focus"],
        whats_on_mind=row["whats_on_mind"],
        period_description=row["period_description"],
    )


def fetch_contact(phone: str) -> Contact:
    with _get_conn().cursor() as cur:
        cur.execute(
            """
            SELECT phone_number, name, relationship_tier, language_primary,
                   language_secondary, texting_style, personality_summary,
                   current_life_situation, trust_level, risk_level, relationship_goal
            FROM contacts WHERE phone_number = %s
            """,
            (phone,),
        )
        row = cur.fetchone()
    if not row:
        raise ValueError(f"contact {phone} not found")
    return Contact(**row)


def fetch_contact_state(phone: str) -> ContactState:
    with _get_conn().cursor() as cur:
        cur.execute(
            """
            SELECT current_attitude_score, attitude_trend, attitude_trend_duration,
                   last_interaction_at, last_interaction_role, baseline_frequency,
                   conversation_quality_avg, unanswered_message_flag, unanswered_since,
                   pulse_score, last_heartbeat_action, last_heartbeat_at
            FROM contact_state WHERE contact_phone = %s
            """,
            (phone,),
        )
        row = cur.fetchone()
    if not row:
        return ContactState(
            current_attitude_score=0.0,
            attitude_trend="stable",
            attitude_trend_duration=0,
            last_interaction_at=None,
            last_interaction_role=None,
            baseline_frequency=None,
            conversation_quality_avg=0.5,
            unanswered_message_flag=False,
            unanswered_since=None,
            pulse_score=0.0,
            last_heartbeat_action=None,
            last_heartbeat_at=None,
        )
    return ContactState(
        current_attitude_score=row["current_attitude_score"],
        attitude_trend=row["attitude_trend"],
        attitude_trend_duration=row["attitude_trend_duration"],
        last_interaction_at=row["last_interaction_at"].isoformat() if row["last_interaction_at"] else None,
        last_interaction_role=row["last_interaction_role"],
        baseline_frequency=row["baseline_frequency"],
        conversation_quality_avg=row["conversation_quality_avg"],
        unanswered_message_flag=row["unanswered_message_flag"],
        unanswered_since=row["unanswered_since"].isoformat() if row["unanswered_since"] else None,
        pulse_score=row["pulse_score"],
        last_heartbeat_action=row["last_heartbeat_action"],
        last_heartbeat_at=row["last_heartbeat_at"].isoformat() if row["last_heartbeat_at"] else None,
    )


def fetch_per_person_rules(phone: str) -> PerPersonRules | None:
    with _get_conn().cursor() as cur:
        cur.execute(
            """
            SELECT allowed_topics, forbidden_topics, vulnerability_level,
                   humor_allowed, image_to_project, things_to_hide,
                   message_length_style, double_texting
            FROM per_person_rules WHERE contact_phone = %s
            """,
            (phone,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return PerPersonRules(
        allowed_topics=row["allowed_topics"] or [],
        forbidden_topics=row["forbidden_topics"] or [],
        vulnerability_level=row["vulnerability_level"],
        humor_allowed=row["humor_allowed"],
        image_to_project=row["image_to_project"],
        things_to_hide=row["things_to_hide"] or [],
        message_length_style=row["message_length_style"],
        double_texting=row["double_texting"],
    )


def fetch_conversation_history(phone: str) -> list[Message]:
    with _get_conn().cursor() as cur:
        cur.execute(
            """
            SELECT m.role, m.content, m.language, m.sent_at
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE m.contact_phone = %s AND c.state = 'open'
            ORDER BY m.sent_at DESC
            LIMIT %s
            """,
            (phone, HISTORY_LIMIT),
        )
        rows = cur.fetchall()
    return [
        Message(
            role=r["role"],
            content=r["content"],
            language=r["language"],
            sent_at=r["sent_at"].isoformat(),
        )
        for r in reversed(rows)
    ]


def fetch_life_events(phone: str) -> list[LifeEvent]:
    with _get_conn().cursor() as cur:
        cur.execute(
            """
            SELECT event_type, description, event_date, lookahead_days
            FROM life_events
            WHERE contact_phone = %s AND notified = FALSE
            ORDER BY event_date ASC NULLS LAST
            LIMIT %s
            """,
            (phone, LIFE_EVENTS_LIMIT),
        )
        rows = cur.fetchall()
    return [
        LifeEvent(
            event_type=r["event_type"],
            description=r["description"],
            event_date=r["event_date"].isoformat() if r["event_date"] else None,
            lookahead_days=r["lookahead_days"],
        )
        for r in rows
    ]


def fetch_few_shots(language: str, relationship_tier: int) -> list[FewShot]:
    with _get_conn().cursor() as cur:
        cur.execute(
            """
            SELECT context, input, output FROM omar_few_shots
            WHERE language = %s AND relationship_tier = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (language, relationship_tier, FEW_SHOTS_LIMIT),
        )
        rows = cur.fetchall()
    return [FewShot(**r) for r in rows]
