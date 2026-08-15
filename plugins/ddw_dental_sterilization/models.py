"""DDW Dental Sterilization - 数据模型."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

CYCLE_TYPES = ("autoclave", "chemical", "uv")
INDICATOR_RESULTS = ("pass", "fail")


class Sterilizer(BaseModel):
    id: Optional[str] = None
    name: str
    model: Optional[str] = None
    location: Optional[str] = None
    last_calibration: Optional[str] = None
    is_active: bool = True


class SterilizerCreate(BaseModel):
    name: str
    model: Optional[str] = None
    location: Optional[str] = None
    last_calibration: Optional[str] = None


class SterilizationBatch(BaseModel):
    id: Optional[str] = None
    batch_number: str
    instruments: list[str] = Field(default_factory=list)
    sterilizer_id: str
    cycle_type: str
    start_time: datetime
    end_time: datetime
    temperature: Optional[float] = None
    pressure: Optional[float] = None
    indicator_result: str = "pass"
    operator: str
    expiry_date: str
    used_by_record_id: Optional[str] = None
    created_at: Optional[datetime] = None


class BatchCreate(BaseModel):
    batch_number: str
    instruments: list[str] = Field(default_factory=list)
    sterilizer_id: str
    cycle_type: str
    start_time: datetime
    end_time: datetime
    temperature: Optional[float] = None
    pressure: Optional[float] = None
    indicator_result: str = "pass"
    operator: str
    expiry_date: str
    used_by_record_id: Optional[str] = None


class BatchList(BaseModel):
    total: int
    batches: list[SterilizationBatch]


class TraceResponse(BaseModel):
    batch_id: str
    patients: list[str]
    record_ids: list[str]


class ComplianceResponse(BaseModel):
    period: str
    total_batches: int
    pass_rate: float
    failed_batches: int
    expired_used: int
    instruments_traced: int


class HealthResponse(BaseModel):
    plugin: str = "ddw_dental_sterilization"
    version: str = "0.1.0"
    status: str = "ok"
    total_batches: int = 0
    total_sterilizers: int = 0
