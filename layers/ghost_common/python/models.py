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


class MoodEngineRequest(BaseModel):
    contact_phone: str
    conversation_id: str
    recent_messages: list[dict[str, Any]] = Field(default_factory=list)
    contact_context: dict[str, Any] = Field(default_factory=dict)


class MoodEngineResponse(BaseModel):
    mood_state: MoodState
    signals_used: list[str] = Field(default_factory=list)


class TimingEngineRequest(BaseModel):
    contact_phone: str
    conversation_id: str
    mood_state: MoodState
    last_message_at: datetime


class TimingEngineResponse(BaseModel):
    reply_now: bool
    delay_seconds: int = 0
    reasoning: str = ""


class EscalationDetectorRequest(BaseModel):
    contact_phone: str
    message_content: str
    conversation_id: str
    message_id: str


class EscalationDetectorResponse(BaseModel):
    is_escalation: bool
    reason: Optional[str] = None
    confidence: float = 0.0


class MemoryRetrieverRequest(BaseModel):
    contact_phone: str
    query: str
    limit: int = 5


class MemoryRetrieverResponse(BaseModel):
    chunks: list[dict[str, Any]] = Field(default_factory=list)


class ResponseGeneratorRequest(BaseModel):
    contact_phone: str
    conversation_id: str
    inbound_message: str
    mood_state: MoodState
    memory_chunks: list[dict[str, Any]] = Field(default_factory=list)
    voice_profile: Optional[dict[str, Any]] = None


class ResponseGeneratorResponse(BaseModel):
    reply: str
    confidence_score: float = 1.0


class WhatsAppSenderRequest(BaseModel):
    """Payload sent to the whatsapp_sender Lambda."""
    to_phone_number: str
    message: str
    message_id: Optional[str] = None


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
