from __future__ import annotations

from typing import List, Optional

"""DDW 经销商开户插件 Pydantic schemas。"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# 枚举常量（与 manifest.yaml / models.py 注释保持一致）
# ---------------------------------------------------------------------------

PARTNER_TYPES = {"reseller", "agent", "distributor"}
LEVELS = {"normal", "silver", "gold", "strategic"}
STATUSES = {"active", "inactive", "suspended"}


# ---------------------------------------------------------------------------
# 经销商 demo 账号清单（名下客户演示账号）
# ---------------------------------------------------------------------------


class DemoAccountCreateReq(BaseModel):
    """新建客户 demo 账号（经销商名下）。"""

    client_tenant_id: Optional[int] = Field(None, description="客户租户 ID")
    client_name: str = Field(..., min_length=1, max_length=200, description="客户名称")
    client_industry: Optional[str] = Field(None, max_length=100, description="客户行业")
    demo_url: str = Field(..., min_length=1, max_length=500, description="demo 登录地址")
    demo_phone: str = Field(..., min_length=11, max_length=20, description="demo 账号手机号")
    demo_password: str = Field(..., min_length=1, max_length=128, description="demo 账号密码")
    demo_note: Optional[str] = Field(None, max_length=500, description="备注")
    expires_at: Optional[datetime] = Field(None, description="过期时间")


class DemoAccountUpdateReq(BaseModel):
    """更新 demo 账号。"""

    client_name: Optional[str] = Field(None, max_length=200)
    client_industry: Optional[str] = Field(None, max_length=100)
    demo_url: Optional[str] = Field(None, max_length=500)
    demo_phone: Optional[str] = Field(None, max_length=20)
    demo_password: Optional[str] = Field(None, max_length=128)
    demo_note: Optional[str] = Field(None, max_length=500)
    status: Optional[str] = Field(None, pattern="^(active|expired|disabled)$")
    expires_at: Optional[datetime] = Field(None)


class DemoAccountResp(BaseModel):
    """demo 账号响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_tenant_id: Optional[int]
    client_name: str
    client_industry: Optional[str]
    demo_url: str
    demo_phone: str
    demo_password: str
    demo_note: Optional[str]
    status: str
    expires_at: Optional[datetime]
    created_at: datetime


class DemoAccountListResp(BaseModel):
    """demo 账号列表响应。"""

    total: int
    items: List[DemoAccountResp]


class EnterDemoReq(BaseModel):
    """经销商一键进入 demo 请求。"""

    account_id: int = Field(..., description="demo 账号 ID")


class EnterDemoResp(BaseModel):
    """经销商一键进入 demo 响应。"""

    demo_token: str
    demo_url: str
    expires_in: int = 900


class PaidCustomer(BaseModel):
    """付费客户列表项。"""

    model_config = ConfigDict(from_attributes=True)

    client_tenant_id: Optional[int] = None
    client_name: str
    plan: str
    status: str
    contact_phone: Optional[str] = None
    expires_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


class PartnerCreateReq(BaseModel):
    """新建经销商开户请求。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")

    # 关联（可空）
    company_id: Optional[int] = Field(None, description="关联客户企业 ID（可空）")

    # 分类
    partner_type: str = Field(
        "reseller", description="经销商类型：reseller / agent / distributor"
    )
    level: str = Field("normal", description="等级：normal / silver / gold / strategic")

    # 区域 / 行业
    region: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = Field(None, max_length=100)

    # 可售范围 / 折扣
    allowed_products: Optional[List[str]] = Field(
        None, description="可售产品/插件范围（标识符列表）"
    )
    product_discount: Optional[Decimal] = Field(
        Decimal(80), ge=0, le=100, description="产品折扣（百分数，80 = 8 折）"
    )
    plugin_discount: Optional[Decimal] = Field(
        Decimal(85), ge=0, le=100, description="插件折扣（百分数）"
    )
    service_discount: Optional[Decimal] = Field(
        Decimal(90), ge=0, le=100, description="服务折扣（百分数）"
    )

    # 合作期
    agreement_start: Optional[date] = None
    agreement_end: Optional[date] = None

    # 联系人
    contact_person: Optional[str] = Field(None, max_length=50)
    contact_phone: Optional[str] = Field(None, max_length=20)

    # 备注
    notes: Optional[str] = None

    # 审计
    created_by: Optional[int] = None

    @field_validator("partner_type")
    @classmethod
    def _check_partner_type(cls, v: str) -> str:
        if v not in PARTNER_TYPES:
            raise ValueError(
                f"partner_type 必须是 {sorted(PARTNER_TYPES)} 之一，得到 {v!r}"
            )
        return v

    @field_validator("level")
    @classmethod
    def _check_level(cls, v: str) -> str:
        if v not in LEVELS:
            raise ValueError(f"level 必须是 {sorted(LEVELS)} 之一，得到 {v!r}")
        return v

    @field_validator("agreement_end")
    @classmethod
    def _check_agreement_range(cls, v: Optional[date], info) -> Optional[date]:
        start = info.data.get("agreement_start")
        if v is not None and start is not None and v < start:
            raise ValueError("agreement_end 不能早于 agreement_start")
        return v


# ---------------------------------------------------------------------------
# 更新（全字段可选）
# ---------------------------------------------------------------------------


class PartnerUpdateReq(BaseModel):
    """更新经销商请求（全字段可选）。"""

    company_id: Optional[int] = None

    partner_type: Optional[str] = None
    level: Optional[str] = None

    region: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = Field(None, max_length=100)

    allowed_products: Optional[List[str]] = None
    product_discount: Optional[Decimal] = Field(None, ge=0, le=100)
    plugin_discount: Optional[Decimal] = Field(None, ge=0, le=100)
    service_discount: Optional[Decimal] = Field(None, ge=0, le=100)

    agreement_start: Optional[date] = None
    agreement_end: Optional[date] = None

    contact_person: Optional[str] = Field(None, max_length=50)
    contact_phone: Optional[str] = Field(None, max_length=20)

    status: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("partner_type")
    @classmethod
    def _check_partner_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in PARTNER_TYPES:
            raise ValueError(
                f"partner_type 必须是 {sorted(PARTNER_TYPES)} 之一，得到 {v!r}"
            )
        return v

    @field_validator("level")
    @classmethod
    def _check_level(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in LEVELS:
            raise ValueError(f"level 必须是 {sorted(LEVELS)} 之一，得到 {v!r}")
        return v

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in STATUSES:
            raise ValueError(f"status 必须是 {sorted(STATUSES)} 之一，得到 {v!r}")
        return v


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class PartnerResp(BaseModel):
    """经销商响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int

    company_id: Optional[int] = None

    partner_type: str
    level: str

    region: Optional[str] = None
    industry: Optional[str] = None

    allowed_products: Optional[List[str]] = None
    product_discount: Decimal
    plugin_discount: Decimal
    service_discount: Decimal

    agreement_start: Optional[date] = None
    agreement_end: Optional[date] = None

    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None

    status: str
    notes: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None


class PartnerListResp(BaseModel):
    """经销商分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[PartnerResp]


class PartnerStatsResp(BaseModel):
    """经销商统计概览。"""

    total: int
    active: int
    inactive: int
    suspended: int
    by_partner_type: dict[str, int]
    by_level: dict[str, int]
    by_region: dict[str, int]


__all__ = [
    "LEVELS",
    "PARTNER_TYPES",
    "STATUSES",
    "PartnerCreateReq",
    "PartnerListResp",
    "PartnerResp",
    "PartnerStatsResp",
    "PartnerUpdateReq",
]
