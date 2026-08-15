"""DDW Dental EMR - 数据模型."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from ddw_clinical_asr.schema import TREATMENT_VALUES
from pydantic import BaseModel, Field


class DentalRecord(BaseModel):
    """病历主数据."""

    id: Optional[str] = None
    patient_id: str
    doctor_id: str
    treatment_type: str  # 9 类诊疗
    chief_complaint: str
    present_illness: str
    past_history: Optional[str] = None
    examination: dict[str, Any] = Field(default_factory=dict)
    diagnosis: str
    treatment_plan: str
    special_findings: dict[str, Any] = Field(default_factory=dict)
    urgency: str = "routine"  # routine/urgent/emergency
    status: str = "draft"     # draft/reviewed/finalized
    transcript_job_id: Optional[str] = None
    images: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DentalRecordCreate(BaseModel):
    """创建病历请求（不含 id/timestamps）."""

    patient_id: str
    doctor_id: str
    treatment_type: str
    chief_complaint: str
    present_illness: str
    past_history: Optional[str] = None
    examination: dict[str, Any] = Field(default_factory=dict)
    diagnosis: str
    treatment_plan: str
    special_findings: dict[str, Any] = Field(default_factory=dict)
    urgency: str = "routine"
    transcript_job_id: Optional[str] = None
    images: list[str] = Field(default_factory=list)


class DentalRecordListResponse(BaseModel):
    total: int
    records: list[DentalRecord]
    page: int = 1
    page_size: int = 20


class StatusUpdate(BaseModel):
    status: str  # draft/reviewed/finalized
    notes: Optional[str] = None


class FromTranscriptRequest(BaseModel):
    transcript_job_id: str
    patient_id: str
    doctor_id: str
    treatment_hint: Optional[str] = None


class FromTranscriptResponse(BaseModel):
    status: str = "ok"
    record: DentalRecord
    validation: dict[str, Any] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    plugin: str = "ddw_dental_emr"
    version: str = "0.1.0"
    status: str = "ok"
    total_records: int = 0
    template_count: int = 0
    available_types: list[str] = list(TREATMENT_VALUES)
