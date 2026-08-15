from __future__ import annotations

"""DDW 报价单管理插件 Pydantic schemas。

包含：
- QuotationItemReq / QuotationItemResp：明细行请求与响应
- QuotationCreateReq：创建报价单（含 items 列表）
- QuotationUpdateReq：更新报价单（全字段可选，items 整体替换）
- QuotationResp：报价单响应（含 items）
- QuotationListResp：分页列表
- QuotationStatsResp：统计概览
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 明细（QuotationItem）
# ---------------------------------------------------------------------------


class QuotationItemReq(BaseModel):
    """报价单明细请求（创建 / 更新时复用）。"""

    product_name: str = Field(..., min_length=1, max_length=200, description="产品/服务名称")
    product_type: Optional[str] = Field(
        None, max_length=30, description="产品类型：product/plugin/service/token"
    )
    product_code: Optional[str] = Field(None, max_length=50)
    quantity: int = Field(1, ge=1, description="数量（>=1）")
    unit: str = Field("套", max_length=20, description="单位（套/件/人天/月...）")
    unit_price: Optional[Decimal] = Field(None, ge=0, description="单价")
    amount: Optional[Decimal] = Field(
        None, ge=0, description="金额（=quantity × unit_price；不传则服务端计算）"
    )
    description: Optional[str] = None
    sort_order: int = Field(0, ge=0, description="排序号（升序）")


class QuotationItemResp(BaseModel):
    """报价单明细响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    quotation_id: int
    product_name: str
    product_type: Optional[str] = None
    product_code: Optional[str] = None
    quantity: int
    unit: str
    unit_price: Optional[Decimal] = None
    amount: Optional[Decimal] = None
    description: Optional[str] = None
    sort_order: int
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# 创建 / 更新
# ---------------------------------------------------------------------------


class QuotationCreateReq(BaseModel):
    """新建报价单请求（必带 items 列表）。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")

    company_id: Optional[int] = Field(None, description="关联客户企业 ID")
    contact_id: Optional[int] = Field(None, description="关联联系人 ID")
    opportunity_id: Optional[int] = Field(None, description="关联商机 ID")

    title: Optional[str] = Field(None, max_length=200)
    discount_rate: Optional[Decimal] = Field(
        Decimal("100"),
        ge=0,
        le=100,
        description="折扣率（百分比，100 = 不打折）",
    )
    currency: str = Field("CNY", min_length=1, max_length=10, description="币种")
    valid_until: Optional[date] = Field(None, description="有效期截止日")
    terms: Optional[str] = None
    notes: Optional[str] = None

    items: List[QuotationItemReq] = Field(
        default_factory=list, description="明细列表（至少 1 条）"
    )

    created_by: Optional[int] = Field(None, description="创建人 ID")


class QuotationUpdateReq(BaseModel):
    """更新报价单请求（全字段可选；items 非空则整体替换）。"""

    company_id: Optional[int] = None
    contact_id: Optional[int] = None
    opportunity_id: Optional[int] = None

    title: Optional[str] = Field(None, max_length=200)
    discount_rate: Optional[Decimal] = Field(None, ge=0, le=100)
    currency: Optional[str] = Field(None, min_length=1, max_length=10)
    valid_until: Optional[date] = None
    terms: Optional[str] = None
    notes: Optional[str] = None

    items: Optional[List[QuotationItemReq]] = Field(
        None, description="明细列表（不传则保留；传 [] 则清空；非空则整体替换）"
    )


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class QuotationResp(BaseModel):
    """报价单响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int

    company_id: Optional[int] = None
    contact_id: Optional[int] = None
    opportunity_id: Optional[int] = None

    quotation_no: str
    title: Optional[str] = None

    total_amount: Optional[Decimal] = None
    discount_rate: Optional[Decimal] = None
    final_amount: Optional[Decimal] = None
    currency: str

    valid_until: Optional[date] = None
    terms: Optional[str] = None
    notes: Optional[str] = None

    status: str
    sent_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    rejected_at: Optional[datetime] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None

    # 明细列表（详情/创建/更新时填充；列表接口可为空）
    items: List[QuotationItemResp] = Field(default_factory=list)


class QuotationListResp(BaseModel):
    """报价单分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[QuotationResp]


class QuotationStatsResp(BaseModel):
    """报价单统计概览。"""

    total: int
    draft: int
    sent: int
    accepted: int
    rejected: int
    expired: int
    total_amount: Decimal = Field(Decimal("0"), description="所有报价单的 final_amount 之和")
    accepted_amount: Decimal = Field(
        Decimal("0"), description="已接受报价单的 final_amount 之和"
    )


__all__ = [
    "QuotationCreateReq",
    "QuotationItemReq",
    "QuotationItemResp",
    "QuotationListResp",
    "QuotationResp",
    "QuotationStatsResp",
    "QuotationUpdateReq",
]
