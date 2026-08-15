"""SQLAlchemy ORM models and Pydantic schemas for ESG chatbot."""

import datetime
import uuid
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import JSON, Column, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# SQLAlchemy ORM models
# ---------------------------------------------------------------------------

class ChatSession(Base):
    __tablename__ = "esg_chatbot_sessions"

    id = Column(String(16), primary_key=True, default=_uuid)
    user_id = Column(String(64), nullable=False, index=True)
    company_id = Column(String(64), index=True)
    topic = Column(String(256), default="")
    status = Column(String(16), default="active")  # active|closed|escalated
    metadata_ = Column("metadata", JSON, default=dict)
    message_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )
    messages = relationship(
        "ChatMessage",
        back_populates="session",
        order_by="ChatMessage.created_at",
    )
    escalations = relationship("Escalation", back_populates="session")

    __table_args__ = (
        Index("ix_esg_chatbot_sessions_user_status", "user_id", "status"),
    )


class ChatMessage(Base):
    __tablename__ = "esg_chatbot_messages"

    id = Column(String(16), primary_key=True, default=_uuid)
    session_id = Column(String(16), nullable=False, index=True)
    role = Column(String(16), nullable=False)  # user|assistant|system
    content = Column(Text, nullable=False)
    confidence = Column(Float)
    sources = Column(JSON, default=list)
    tokens_prompt = Column(Integer)
    tokens_completion = Column(Integer)
    model = Column(String(64))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    session = relationship("ChatSession", back_populates="messages")

    __table_args__ = (
        Index("ix_esg_chatbot_messages_session", "session_id", "created_at"),
    )


class Escalation(Base):
    __tablename__ = "esg_chatbot_escalations"

    id = Column(String(16), primary_key=True, default=_uuid)
    session_id = Column(String(16), nullable=False, index=True)
    reason = Column(Text)
    priority = Column(String(16), default="normal")  # low|normal|high|urgent
    status = Column(String(16), default="pending")  # pending|assigned|resolved|cancelled
    assigned_to = Column(String(64))
    contact_info = Column(JSON, default=dict)
    context_summary = Column(Text)
    estimated_wait_minutes = Column(Integer, default=15)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    resolved_at = Column(DateTime)
    session = relationship("ChatSession", back_populates="escalations")


# ---------------------------------------------------------------------------
# Pydantic request / response schemas
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    session_id: str = Field(..., description="Chat session ID")
    message: str = Field(..., min_length=1, max_length=4000, description="User message")
    user_id: str = Field(default="anonymous", description="User identifier")


class ChatResponse(BaseModel):
    session_id: str
    message_id: str
    reply: str
    confidence: float
    sources: list[dict] = Field(default_factory=list)
    tokens_used: dict = Field(default_factory=dict)
    should_escalate: bool = False


class SessionCreate(BaseModel):
    user_id: str = Field(..., description="User identifier")
    company_id: Optional[str] = None
    topic: str = ""
    metadata: dict = Field(default_factory=dict)


class SessionResponse(BaseModel):
    id: str
    user_id: str
    company_id: Optional[str] = None
    topic: str
    status: str
    metadata: dict = Field(default_factory=dict)
    message_count: int
    created_at: str
    updated_at: str


class MessageResponse(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    confidence: Optional[float] = None
    sources: list[dict] = Field(default_factory=list)
    tokens_prompt: Optional[int] = None
    tokens_completion: Optional[int] = None
    model: Optional[str] = None
    created_at: str


class EscalationRequest(BaseModel):
    session_id: str = Field(..., description="Chat session ID")
    reason: str = Field(..., description="Reason for escalation")
    priority: str = Field(default="normal", pattern=r"^(low|normal|high|urgent)$")
    contact_info: dict = Field(default_factory=dict)


class EscalationResponse(BaseModel):
    id: str
    session_id: str
    reason: str
    priority: str
    status: str
    assigned_to: Optional[str] = None
    contact_info: dict = Field(default_factory=dict)
    context_summary: str = ""
    estimated_wait_minutes: int = 15
    created_at: str
    resolved_at: Optional[str] = None


class KnowledgeStats(BaseModel):
    total_documents: int = 0
    total_chunks: int = 0
    last_indexed: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    llm_gateway: bool
    knowledge_base: bool
    version: str
