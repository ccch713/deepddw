"""DDW Informed Consent - 数据模型."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

CONSENT_TYPES = ("treatment", "anesthesia", "surgery", "financial")
STATUSES = ("pending", "signed", "revoked")

DEFAULT_TEMPLATES = [
    {"name": "拔牙知情同意书", "consent_type": "treatment"},
    {"name": "根管治疗知情同意书", "consent_type": "treatment"},
    {"name": "种植手术知情同意书", "consent_type": "surgery"},
    {"name": "正畸治疗知情同意书", "consent_type": "treatment"},
    {"name": "美容修复知情同意书", "consent_type": "treatment"},
    {"name": "麻醉知情同意书", "consent_type": "anesthesia"},
    {"name": "费用知情同意书", "consent_type": "financial"},
]


class ConsentRecord(BaseModel):
    id: Optional[str] = None
    patient_id: str
    record_id: Optional[str] = None
    consent_type: str
    template_content: str
    patient_signature: Optional[str] = None
    signed_at: Optional[datetime] = None
    witness: Optional[str] = None
    audio_path: Optional[str] = None
    status: str = "pending"
    created_at: Optional[datetime] = None


class ConsentCreate(BaseModel):
    patient_id: str
    record_id: Optional[str] = None
    consent_type: str
    template_content: str
    witness: Optional[str] = None
    audio_path: Optional[str] = None


class ConsentSign(BaseModel):
    patient_signature: str
    witness: Optional[str] = None


class TemplateInfo(BaseModel):
    name: str
    consent_type: str


class TemplateList(BaseModel):
    total: int
    templates: list[TemplateInfo]


class ConsentList(BaseModel):
    total: int
    records: list[ConsentRecord]


class HealthResponse(BaseModel):
    plugin: str = "ddw_informed_consent"
    version: str = "0.1.0"
    status: str = "ok"
    total_consents: int = 0
