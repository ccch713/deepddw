"""Pydantic models for ESG report request/response."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ScoreLevel(str, Enum):
    """Assessment score level classification."""

    excellent = "excellent"
    good = "good"
    medium = "medium"
    poor = "poor"
    fail = "fail"


class ThemeScore(BaseModel):
    """Score for a single ESG theme/dimension."""

    id: str
    name: str
    score: float = Field(ge=0, le=100, description="Score from 0 to 100")
    level: ScoreLevel
    color: str = "#34C759"
    max_score: float = Field(gt=0, default=100)


class FrameworkScore(BaseModel):
    """Score breakdown per reporting framework."""

    framework: str
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)


class MetaAnalysis(BaseModel):
    """Statistical meta analysis of theme scores."""

    average: float
    balance: str
    std_dev: float
    total_desc: str
    dimensions: List[dict] = []
    weak: List[dict] = []


class Recommendation(BaseModel):
    """A single priority-tagged recommendation."""

    priority: str = Field(description="Priority level: 高/中/低")
    text: str
    area: Optional[str] = None


class ReportGenerateRequest(BaseModel):
    """Request body for PDF report generation."""

    assessment_id: str
    company_name: str = "ESG Assessment Report"
    assessment_date: str
    framework: dict = {}
    overall: dict = {}
    themes: List[ThemeScore] = Field(min_length=1, description="At least one theme score required")
    framework_scores: List[FrameworkScore] = []
    meta_analysis: Optional[MetaAnalysis] = None
    recommendations: List[Recommendation] = []


class ReportGenerateResponse(BaseModel):
    """Response body after successful report generation."""

    report_id: str
    assessment_id: str
    download_url: str
    file_size_bytes: int
    pages: int
    generated_at: str
    duration_ms: int


class ReportMetadata(BaseModel):
    """Metadata for a previously generated report."""

    report_id: str
    assessment_id: str
    company_name: str
    file_size_bytes: int
    pages: int
    generated_at: str
    file_path: str
