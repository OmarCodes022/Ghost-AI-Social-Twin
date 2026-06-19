from typing import List
from pydantic import BaseModel


class InboundMessage(BaseModel):
    phone_number: str
    name: str
    whatsapp_message_id: str
    content: str
    timestamp: str
    message_type: str = "text"


class Classification(BaseModel):
    language: str        # 'french' | 'english' | 'arabic'
    emotion: str         # e.g. 'dry', 'worried', 'excited', 'flat', 'warm'
    intent: str          # e.g. 'checking_in', 'question', 'venting', 'greeting'
    urgency: str         # 'high' | 'medium' | 'low'
    attitude_shift: float  # -1.0 (very negative) to +1.0 (very positive)
    sensitivity_flags: List[str]  # e.g. ['suicidal', 'crisis', 'threat']
    topic_summary: str   # one short sentence


class PerceptionOutput(BaseModel):
    contact_phone: str
    conversation_id: str
    message_id: str
    content: str
    classification: Classification
    triggered_at: str
