"""Data models for the ESG question bank plugin.

Domain models (dataclasses) for framework/theme/indicator/question structures,
and Pydantic models for API request/response schemas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

# ── Domain enums ──────────────────────────────────────────────────────────────

class StandardCategory(str, Enum):
    INTERNATIONAL = "international"
    FOREIGN = "foreign"
    NATIONAL = "national"
    ASSOCIATION = "association"


class FrameworkStatus(str, Enum):
    AVAILABLE = "available"
    DRAFT = "draft"
    COMING_SOON = "coming-soon"


class ThemeCategory(str, Enum):
    ENVIRONMENT = "environment"
    SOCIAL = "social"
    GOVERNANCE = "governance"
    PROCUREMENT = "procurement"


class QuestionType(str, Enum):
    LIKERT5 = "likert5"
    YESNO = "yesno"
    MULTIPLE_CHOICE = "multiple_choice"
    NUMERIC = "numeric"


class ScoreLevel(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    MEDIUM = "medium"
    POOR = "poor"
    FAIL = "fail"


class CompanySize(str, Enum):
    MICRO = "micro"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    ENTERPRISE = "enterprise"


# ── Domain dataclasses ────────────────────────────────────────────────────────

@dataclass
class QuestionOption:
    value: int
    label: str
    weight: Optional[float] = None


@dataclass
class Question:
    id: str
    text: str
    type: QuestionType
    options: list[QuestionOption]
    required: bool
    score_range: tuple[int, int]
    default_score: Optional[int] = None
    help_text: Optional[str] = None
    evidence_required: Optional[list[str]] = None
    display_order: Optional[int] = None
    theme_id: Optional[str] = None
    indicator_code: Optional[str] = None
    skip_rules: Optional[list[dict]] = None
    show_condition: Optional[dict] = None


@dataclass
class Indicator:
    code: str
    name: str
    theme_id: str
    weight: float
    description: Optional[str] = None
    questions: list[Question] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    suggestions: list[dict] = field(default_factory=list)


@dataclass
class Theme:
    id: str
    name: str
    category: ThemeCategory
    weight: float
    description: Optional[str] = None
    color: Optional[str] = None


@dataclass
class RatingLevel:
    code: str
    name: str
    min_score: int
    max_score: int
    description: str
    prerequisites: Optional[list[str]] = None


@dataclass
class Framework:
    id: str
    name: str
    organization: str
    url: str
    description: str
    supported_sizes: list[CompanySize]
    themes: list[Theme]
    indicators: list[Indicator]
    version: str
    category: StandardCategory = StandardCategory.NATIONAL
    status: FrameworkStatus = FrameworkStatus.AVAILABLE
    standard_code: Optional[str] = None
    is_mandatory: bool = False
    issuing_body: Optional[str] = None
    issue_date: Optional[str] = None
    effective_date: Optional[str] = None
    category_color: Optional[str] = None
    rating_levels: Optional[list[RatingLevel]] = None


# ── Pydantic API models ──────────────────────────────────────────────────────

class AnswerItem(BaseModel):
    question_id: str = Field(..., description="Question ID, e.g. E1-Q1")
    value: int = Field(..., description="Selected answer value")


class AssessRequest(BaseModel):
    framework_id: str = Field(..., description="Framework ID, e.g. standard-esg")
    answers: list[AnswerItem] = Field(..., description="List of question answers")
    company_size: Optional[str] = Field(None, description="Company size hint")


class ThemeScore(BaseModel):
    theme_id: str
    theme_name: str
    score: float
    weight: float
    question_count: int
    answered_count: int


class IndicatorScore(BaseModel):
    indicator_code: str
    indicator_name: str
    theme_id: str
    score: float
    weight: float


class ScoreLevelInfo(BaseModel):
    code: str
    label: str
    label_en: str
    min: int
    max: int
    color: str
    description: str


class AssessResponse(BaseModel):
    framework_id: str
    total_score: float
    level: str
    level_label: str
    level_color: str
    theme_scores: list[ThemeScore]
    indicator_scores: list[IndicatorScore]
    total_questions: int
    answered_questions: int
    completion_rate: float


class FrameworkSummary(BaseModel):
    id: str
    name: str
    organization: str
    description: str
    category: str
    status: str
    question_count: int
    theme_count: int
    is_mandatory: bool = False
    supported_sizes: list[str] = []


class FrameworkDetail(BaseModel):
    id: str
    name: str
    organization: str
    url: str
    description: str
    category: str
    status: str
    version: str
    standard_code: Optional[str] = None
    is_mandatory: bool = False
    issuing_body: Optional[str] = None
    issue_date: Optional[str] = None
    effective_date: Optional[str] = None
    supported_sizes: list[str] = []
    themes: list[dict[str, Any]] = []
    indicators: list[dict[str, Any]] = []


class QuestionBankMeta(BaseModel):
    framework_id: str
    framework_name: str
    total_questions: int
    total_indicators: int
    total_themes: int
    themes: list[dict[str, Any]] = []
    indicators: list[dict[str, Any]] = []


class HealthResponse(BaseModel):
    plugin: str
    status: str
    frameworks_loaded: int = 0


class SearchResult(BaseModel):
    id: str
    name: str
    organization: str
    description: str
    relevance_score: float = 1.0
