"""SQLAlchemy ORM models and Pydantic schemas for ESG assessment."""

from __future__ import annotations

from typing import Any, Optional, Union
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Float, String, func
from sqlalchemy.orm import DeclarativeBase

# ---------------------------------------------------------------------------
# SQLAlchemy ORM
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class Assessment(Base):
    """Persisted assessment record."""

    __tablename__ = "esg_assessments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(64), nullable=False, index=True)
    framework_id = Column(String(32), nullable=False, index=True)
    company_name = Column(String(256))
    company_size = Column(String(16))
    industry = Column(String(128))
    status = Column(String(16), default="in_progress", index=True)
    answers = Column(String, default="{}")  # JSON stored as text for portability
    theme_scores = Column(String, default="{}")
    indicator_scores = Column(String, default="{}")
    total_score = Column(Float)
    grade = Column(String(32))
    benchmark_results = Column(String, default="{}")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())


# ---------------------------------------------------------------------------
# In-memory store (fallback when no DB)
# ---------------------------------------------------------------------------

_in_memory_store: dict[str, dict[str, Any]] = {}


def get_store() -> dict[str, dict[str, Any]]:
    return _in_memory_store


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class FrameworkMeta(BaseModel):
    id: str
    name: str
    name_en: str
    themes: list[ThemeMeta]


class ThemeMeta(BaseModel):
    id: str
    name: str
    weight: float = 1.0
    question_count: int


class QuestionOption(BaseModel):
    value: int
    label: str
    label_en: str = ""


class SkipRule(BaseModel):
    type: str  # forward_skip | forward_jump | conditional_show | branch
    condition: Optional[dict[str, Any]] = None
    target: Optional[Union[str, list[str]]] = None


class QuestionMeta(BaseModel):
    id: str
    theme_id: str
    text: str
    text_en: str = ""
    options: list[QuestionOption]
    max_score: int = 4
    skip_rules: list[SkipRule] = []
    dimension: str = ""  # E / S / G


class CreateAssessmentRequest(BaseModel):
    user_id: str
    framework_id: str = "ecovadis"
    company_name: str = ""
    company_size: str = ""
    industry: str = ""


class AssessmentResponse(BaseModel):
    id: str
    user_id: str
    framework_id: str
    company_name: str = ""
    company_size: str = ""
    industry: str = ""
    status: str
    answers: dict[str, Any] = {}
    theme_scores: dict[str, float] = {}
    indicator_scores: dict[str, float] = {}
    total_score: Optional[float] = None
    grade: Optional[str] = None
    benchmark_results: dict[str, Any] = {}
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AnswerRequest(BaseModel):
    question_id: str
    value: int
    comment: str = ""


class SkipResult(BaseModel):
    skipped_ids: list[str] = []
    jump_to: Optional[str] = None
    has_skip: bool = False


class NextQuestionResponse(BaseModel):
    question: Optional[QuestionMeta] = None
    skip_result: Optional[SkipResult] = None
    is_complete: bool = False


class CalculateResponse(BaseModel):
    theme_scores: dict[str, float]
    indicator_scores: dict[str, float]
    total_score: float
    grade: str
    level_cn: str
    benchmark_results: dict[str, Any]


class QuestionBankMeta(BaseModel):
    total_questions: int
    themes: list[ThemeMeta]
    dimensions: list[str]
