from typing import Optional, List
from pydantic import BaseModel


class GhostState(BaseModel):
    mood: Optional[str]
    social_battery: float
    emotional_load: float
    current_focus: Optional[str]
    whats_on_mind: Optional[str]
    period_description: Optional[str]


class Contact(BaseModel):
    phone_number: str
    name: str
    relationship_tier: int
    language_primary: str
    language_secondary: Optional[str]
    texting_style: dict
    personality_summary: Optional[str]
    current_life_situation: Optional[str]
    trust_level: float
    risk_level: float
    relationship_goal: Optional[str]


class ContactState(BaseModel):
    current_attitude_score: float
    attitude_trend: str
    attitude_trend_duration: int
    last_interaction_at: Optional[str]
    last_interaction_role: Optional[str]
    baseline_frequency: Optional[float]
    conversation_quality_avg: float
    unanswered_message_flag: bool
    unanswered_since: Optional[str]
    pulse_score: float
    last_heartbeat_action: Optional[str]
    last_heartbeat_at: Optional[str]


class PerPersonRules(BaseModel):
    allowed_topics: List[str]
    forbidden_topics: List[str]
    vulnerability_level: float
    humor_allowed: bool
    image_to_project: Optional[str]
    things_to_hide: List[str]
    message_length_style: str
    double_texting: bool


class Message(BaseModel):
    role: str  # 'contact' | 'ghost'
    content: str
    language: Optional[str]
    sent_at: str


class LifeEvent(BaseModel):
    event_type: str
    description: str
    event_date: Optional[str]
    lookahead_days: int


class FewShot(BaseModel):
    context: str
    input: str
    output: str


class Tier1Context(BaseModel):
    ghost_state: GhostState
    contact: Contact
    contact_state: ContactState
    per_person_rules: Optional[PerPersonRules]
    conversation_history: List[Message]
    life_events: List[LifeEvent]
    few_shots: List[FewShot]
    perception: dict  # raw PerceptionOutput from Agent 1
