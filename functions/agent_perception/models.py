from enum import Enum
from typing import Optional
from pydantic import BaseModel


class InboundMessage(BaseModel):
    phone_number: str
    name: str
    whatsapp_message_id: str
    content: str
    timestamp: str
    message_type: str = "text"


class MsgType(str, Enum):
    question = "question"
    statement = "statement"
    greeting = "greeting"
    farewell = "farewell"
    media = "media"
    voice_note = "voice_note"
    other = "other"


class Urgency(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Classification(BaseModel):
    msg_type: MsgType
    urgency: Urgency
    sentiment: str  # positive / neutral / negative
    needs_response: bool
    escalate: bool = False
    notes: Optional[str] = None


class PerceptionOutput(BaseModel):
    contact_phone: str
    conversation_id: str
    message_id: str
    content: str
    classification: Classification
    triggered_at: str
