"""Pydantic v2 models for all inter-Lambda contracts and DB row shapes.

All models use ``model_dump(mode="json")`` when serialising for Lambda payloads
so that datetime / UUID objects become JSON-safe strings automatically.
"""
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Enumerations (mirror DB ENUM types) ─────────────────────────────────────

class ArcState(str, Enum):
    open = "open"
    flowing = "flowing"
    winding_down = "winding_down"
    dormant = "dormant"


class MessageRole(str, Enum):
    user = "user"
    agent = "agent"


class KnowledgeCategory(str, Enum):
    identity = "identity"
    opinion = "opinion"
    relationship = "relationship"
    behavioral = "behavioral"


class KnowledgeSource(str, Enum):
    manual = "manual"
    import_ = "import"
    learned = "learned"


class EscalationResolution(str, Enum):
    sent = "sent"
    edited = "edited"
    skipped = "skipped"
    paused = "paused"


# ─── DB row shapes ────────────────────────────────────────────────────────────

class Contact(BaseModel):
    phone_number: str
    name: Optional[str] = None
    relationship_tier: int = 3
    voice_profile: Optional[dict[str, Any]] = None
    last_interaction: Optional[datetime] = None
    interaction_frequency: float = 0.0
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


class Conversation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    contact_phone: str
    arc_state: ArcState = ArcState.open
    started_at: datetime = Field(default_factory=datetime.utcnow)
    last_message_at: datetime = Field(default_factory=datetime.utcnow)
    message_count: int = 0


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str
    role: MessageRole
    content: str
    sent_at: datetime = Field(default_factory=datetime.utcnow)
    was_delayed: bool = False
    delay_seconds: int = 0
    mood_state_id: Optional[str] = None
    confidence_score: float = 1.0
    escalated: bool = False


class MoodState(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    computed_at: datetime = Field(default_factory=datetime.utcnow)
    energy: float = 0.5
    warmth: float = 0.5
    humor_threshold: float = 0.5
    openness: float = 0.5
    patience: float = 0.5
    signals: dict[str, Any] = Field(default_factory=dict)


class GhostState(BaseModel):
    """Persistent mood/availability state. Single row in ghost_state table."""
    id: int = 1
    energy: float = 0.6
    social_battery: float = 1.0   # depletes across conversations, resets overnight
    emotional_load: float = 0.0   # accumulates from heavy conversations
    availability: str = "deep"    # deep / light / minimal
    notes: Optional[str] = None
    updated_at: Optional[datetime] = None


class KnowledgeChunk(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category: KnowledgeCategory
    content: str
    contact_phone: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    source: KnowledgeSource = KnowledgeSource.manual
    similarity_score: Optional[float] = None  # populated by memory_retriever


class Escalation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message_id: str
    reason: str
    confidence: float
    telegram_message_id: Optional[str] = None
    resolution: Optional[EscalationResolution] = None
    resolved_at: Optional[datetime] = None


# ─── Inter-Lambda contracts ───────────────────────────────────────────────────

class InboundWhatsAppMessage(BaseModel):
    """Parsed inbound WhatsApp message produced by webhook_receiver."""
    phone_number: str
    message_id: str
    content: str
    timestamp: datetime
    message_type: str = "text"
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class OrchestratorEvent(BaseModel):
    """Top-level event envelope sent async to the orchestrator Lambda."""
    inbound_message: InboundWhatsAppMessage
    is_delayed: bool = False  # True when re-invoked from the SQS delay queue



class WhatsAppSenderRequest(BaseModel):
    """Payload sent to the whatsapp_sender Lambda."""
    to_phone_number: str
    message: str
    message_id: Optional[str] = None
    part_index: int = 0  # position in multi-part reply (0 = first)
    inbound_message_id: Optional[str] = None  # inbound WhatsApp msg ID for typing indicator
    reply_to_message_id: Optional[str] = None  # wamid to quote (reply bubble, first part only)


class TelegramEscalationEvent(BaseModel):
    """SNS message body published by orchestrator / escalation_detector."""
    escalation_id: str
    message_id: str
    contact_phone: str
    contact_name: Optional[str] = None
    original_message: str
    proposed_reply: str
    reason: str
    confidence: float
