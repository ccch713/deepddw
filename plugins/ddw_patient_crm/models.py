"""DDW Patient CRM - 数据模型."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

SOURCE_VALUES = ("old_patient", "referral", "online", "walk_in", "unknown")


class Patient(BaseModel):
    id: Optional[str] = None
    name: str
    phone: str
    gender: Optional[str] = None       # male / female / other
    birth_date: Optional[str] = None   # YYYY-MM-DD
    source: str = "unknown"
    tags: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    medical_history: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PatientCreate(BaseModel):
    name: str
    phone: str
    gender: Optional[str] = None
    birth_date: Optional[str] = None
    source: str = "unknown"
    tags: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    medical_history: Optional[str] = None
    notes: Optional[str] = None


class PatientUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[list[str]] = None
    allergies: Optional[list[str]] = None
    medical_history: Optional[str] = None
    notes: Optional[str] = None


class PatientList(BaseModel):
    total: int
    patients: list[Patient]


class VisitSummary(BaseModel):
    record_id: str
    treatment_type: str
    diagnosis: str
    doctor_id: str
    created_at: Optional[str] = None
    status: str = "draft"


class VisitsResponse(BaseModel):
    patient_id: str
    total: int
    visits: list[VisitSummary]


class StatsResponse(BaseModel):
    total_patients: int
    this_month_new: int
    by_source: dict[str, int]
    by_gender: dict[str, int]


class HealthResponse(BaseModel):
    plugin: str = "ddw_patient_crm"
    version: str = "0.1.0"
    status: str = "ok"
    total_patients: int = 0
