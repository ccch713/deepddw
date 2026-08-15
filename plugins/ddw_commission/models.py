"""DDW Commission - 数据模型."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CommissionRule(BaseModel):
    id: Optional[str] = None
    treatment_type: str  # 'general' 表示通用
    doctor_id: Optional[str] = None  # None = 所有医生
    percentage: float
    min_amount: float = 0.0
    is_active: bool = True
    created_at: Optional[datetime] = None


class CommissionRuleCreate(BaseModel):
    treatment_type: str
    doctor_id: Optional[str] = None
    percentage: float
    min_amount: float = 0.0


class CommissionRecord(BaseModel):
    id: Optional[str] = None
    doctor_id: str
    period: str  # YYYY-MM
    total_income: float
    commission_amount: float
    rule_applied: str
    status: str = "pending"  # pending / confirmed / paid
    confirmed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    breakdown: list[dict] = []


class CommissionList(BaseModel):
    total: int
    rules: list[CommissionRule]


class RecordList(BaseModel):
    total: int
    records: list[CommissionRecord]


class HealthResponse(BaseModel):
    plugin: str = "ddw_commission"
    version: str = "0.1.0"
    status: str = "ok"
    total_rules: int = 0
