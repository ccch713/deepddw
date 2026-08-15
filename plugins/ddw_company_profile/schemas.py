from __future__ import annotations

"""DDW 企业主体管理插件 Pydantic schemas。"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


class CompanyCreateReq(BaseModel):
    """新建企业请求。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")
    name: str = Field(..., min_length=1, max_length=200, description="工商注册全名")
    credit_code: Optional[str] = Field(
        None, min_length=18, max_length=18, description="统一社会信用代码（18 位）"
    )
    short_name: Optional[str] = Field(None, max_length=100)
    company_type: Optional[str] = Field(None, max_length=50)
    registered_address: Optional[str] = Field(None, max_length=500)
    legal_representative: Optional[str] = Field(None, max_length=50)
    established_date: Optional[date] = None
    business_license_url: Optional[str] = Field(None, max_length=500)
    business_scope: Optional[str] = None

    invoice_title: Optional[str] = Field(None, max_length=200)
    tax_id: Optional[str] = Field(None, max_length=20)
    bank_name: Optional[str] = Field(None, max_length=100)
    bank_account: Optional[str] = Field(None, max_length=50)
    company_phone: Optional[str] = Field(None, max_length=30)
    company_address: Optional[str] = Field(None, max_length=500)

    industry: Optional[str] = Field(None, max_length=50)
    company_size: Optional[str] = Field(None, max_length=20)
    registered_capital: Optional[Decimal] = None
    annual_revenue: Optional[Decimal] = None

    tags: Optional[List[str]] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 更新（全字段可选）
# ---------------------------------------------------------------------------


class CompanyUpdateReq(BaseModel):
    """更新企业请求。"""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    short_name: Optional[str] = Field(None, max_length=100)
    company_type: Optional[str] = Field(None, max_length=50)
    registered_address: Optional[str] = Field(None, max_length=500)
    legal_representative: Optional[str] = Field(None, max_length=50)
    established_date: Optional[date] = None
    business_license_url: Optional[str] = Field(None, max_length=500)
    business_scope: Optional[str] = None

    certification_status: Optional[str] = None
    certification_expires_at: Optional[date] = None

    invoice_title: Optional[str] = Field(None, max_length=200)
    tax_id: Optional[str] = Field(None, max_length=20)
    bank_name: Optional[str] = Field(None, max_length=100)
    bank_account: Optional[str] = Field(None, max_length=50)
    company_phone: Optional[str] = Field(None, max_length=30)
    company_address: Optional[str] = Field(None, max_length=500)

    industry: Optional[str] = Field(None, max_length=50)
    company_size: Optional[str] = Field(None, max_length=20)
    registered_capital: Optional[Decimal] = None
    annual_revenue: Optional[Decimal] = None

    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    status: Optional[str] = None


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class CompanyResp(BaseModel):
    """企业响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    name: str
    credit_code: Optional[str] = None
    short_name: Optional[str] = None
    company_type: Optional[str] = None
    registered_address: Optional[str] = None
    legal_representative: Optional[str] = None
    established_date: Optional[date] = None
    business_license_url: Optional[str] = None
    business_scope: Optional[str] = None

    certification_status: str
    certification_submitted_at: Optional[datetime] = None
    certification_approved_at: Optional[datetime] = None
    certification_expires_at: Optional[date] = None

    invoice_title: Optional[str] = None
    tax_id: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    company_phone: Optional[str] = None
    company_address: Optional[str] = None

    industry: Optional[str] = None
    company_size: Optional[str] = None
    registered_capital: Optional[Decimal] = None
    annual_revenue: Optional[Decimal] = None

    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    status: str

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None


class CompanyListResp(BaseModel):
    """企业分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[CompanyResp]


class CompanyStatsResp(BaseModel):
    """企业统计概览。"""

    total: int
    active: int
    inactive: int
    archived: int
    by_certification_status: dict[str, int]
    by_company_type: dict[str, int]
    by_industry: dict[str, int]


__all__ = [
    "CompanyCreateReq",
    "CompanyListResp",
    "CompanyResp",
    "CompanyStatsResp",
    "CompanyUpdateReq",
]
