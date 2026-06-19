from typing import Optional
from pydantic import BaseModel


class GhostState(BaseModel):
    energy: float
    mood_summary: Optional[str]
    last_reflection_at: Optional[str]


class Contact(BaseModel):
    phone_number: str
    name: str
    relationship_tier: int
    platform: str
    active: bool


class ContactState(BaseModel):
    status: str
    last_seen_at: Optional[str]
    last_message_at: Optional[str]
    ghost_notes: dict


class Message(BaseModel):
    role: str  # user / ghost
    content: str
    sent_at: str


class LifeEvent(BaseModel):
    event_type: str
    description: str
    event_date: Optional[str]
    importance: float


class FewShot(BaseModel):
    scenario: str
    input_message: str
    ideal_response: str


class Tier1Context(BaseModel):
    ghost_state: GhostState
    contact: Contact
    contact_state: ContactState
    per_person_rules: list[str]
    conversation_history: list[Message]
    life_events: list[LifeEvent]
    few_shots: list[FewShot]
    perception: dict  # raw PerceptionOutput from Agent 1
