"""DDW 人员资质插件 — Pydantic schemas。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 请求
# ---------------------------------------------------------------------------


class CertCreateReq(BaseModel):
    person_name: str = Field(..., min_length=1, max_length=100)
    person_id: str = Field(..., min_length=1, max_length=50)
    cert_type: str = Field(..., min_length=1, max_length=50)
    cert_no: str = Field(..., min_length=1, max_length=100)
    cert_level: Optional[str] = Field(None, max_length=50)
    issue_org: Optional[str] = Field(None, max_length=200)
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    renewal_date: Optional[date] = None
    status: str = "active"
    notes: Optional[str] = None
    tenant_id: int = 1


class CertUpdateReq(BaseModel):
    person_name: Optional[str] = None
    person_id: Optional[str] = None
    cert_type: Optional[str] = None
    cert_no: Optional[str] = None
    cert_level: Optional[str] = None
    issue_org: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    renewal_date: Optional[date] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class CertImportReq(BaseModel):
    """批量导入请求（CSV 文本或 Excel base64）。"""
    format: str = Field("csv", pattern="^(csv|excel)$")
    content: str = Field(..., description="CSV 文本或 base64 Excel")
    tenant_id: int = 1
    skip_header: bool = True


class RenewalCreateReq(BaseModel):
    cert_id: int
    renewal_date: date
    operator: Optional[str] = None
    notes: Optional[str] = None
    tenant_id: int = 1


class RenewalUpdateReq(BaseModel):
    renewal_date: Optional[date] = None
    result: Optional[str] = None
    operator: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None  # pending/passed/failed


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class CertResp(BaseModel):
    id: int
    tenant_id: int
    person_name: str
    person_id: str
    cert_type: str
    cert_no: str
    cert_level: Optional[str] = None
    issue_org: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    renewal_date: Optional[date] = None
    status: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CertListResp(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[CertResp]


class RenewalResp(BaseModel):
    id: int
    tenant_id: int
    cert_id: int
    renewal_date: date
    result: Optional[str] = None
    operator: Optional[str] = None
    notes: Optional[str] = None
    status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RenewalListResp(BaseModel):
    total: int
    items: List[RenewalResp]


class ExpiringItem(BaseModel):
    cert_id: int
    person_name: str
    cert_type: str
    cert_no: str
    expiry_date: date
    days_left: int
    bucket: str  # within_30/within_60/within_90/expired


class ExpiringResp(BaseModel):
    within_30: int
    within_60: int
    within_90: int
    expired: int
    items: List[ExpiringItem]


class StatsResp(BaseModel):
    total: int
    active: int
    expired: int
    renewing: int
    by_type: Dict[str, int]
    by_level: Dict[str, int]


class AlertItem(BaseModel):
    id: int
    cert_id: int
    alert_type: str
    severity: str
    message: str
    is_read: int
    created_at: Optional[datetime] = None


class AlertListResp(BaseModel):
    total: int
    unread: int
    items: List[AlertItem]


class ImportResp(BaseModel):
    success: int
    failed: int
    errors: List[Dict[str, Any]]


class ExportResp(BaseModel):
    filename: str
    content: str  # CSV 文本
    count: int


__all__ = [
    "AlertItem",
    "AlertListResp",
    "CertCreateReq",
    "CertImportReq",
    "CertListResp",
    "CertResp",
    "CertUpdateReq",
    "ExpiringItem",
    "ExpiringResp",
    "ExportResp",
    "ImportResp",
    "RenewalCreateReq",
    "RenewalListResp",
    "RenewalResp",
    "RenewalUpdateReq",
    "StatsResp",
]
