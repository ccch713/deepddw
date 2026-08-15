from __future__ import annotations

"""DDW 客户报备与归属插件 Pydantic schemas。

包含：
- LeadClaimCreateReq：新建报备（expire_at 由服务端按 protection_days 自动计算，不允许传入）
- LeadClaimUpdateReq：更新报备（仅 active 状态可改）
- ReleaseClaimReq：主动释放（可选入参 release_reason）
- LeadClaimResp：报备响应
- LeadClaimListResp：分页列表
- LeadClaimStatsResp：统计概览（total/active/expired/won/lost/released + by_partner）
- LeadClaimConflictResp：冲突查询响应（按 company_id 返回所有报备 + active 计数）
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


class LeadClaimCreateReq(BaseModel):
    """新建报备请求。

    - expire_at 由服务端按 ``claim_date + protection_days`` 自动计算，**不允许传入**
    - protection_days 默认 60（可被调用方覆盖）
    """

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")

    partner_id: Optional[int] = Field(None, description="渠道/销售 ID（crm_partners.id）")
    company_id: Optional[int] = Field(None, description="客户企业 ID（crm_companies.id）")

    claim_date: Optional[datetime] = Field(
        None, description="报备时间；不传则默认 now(UTC)"
    )
    protection_days: int = Field(
        60, ge=1, le=365, description="保护期天数（默认 60，最大 365）"
    )

    contact_person: Optional[str] = Field(None, max_length=50)
    contact_phone: Optional[str] = Field(None, max_length=20)
    opportunity_source: Optional[str] = Field(
        None, max_length=50, description="商机来源：网站/微信/电话/转介绍/..."
    )

    expected_amount: Optional[Decimal] = Field(None, ge=0, description="预计金额")
    follow_up_notes: Optional[str] = None

    notes: Optional[str] = None
    created_by: Optional[int] = Field(None, description="创建人 ID")


# ---------------------------------------------------------------------------
# 更新
# ---------------------------------------------------------------------------


class LeadClaimUpdateReq(BaseModel):
    """更新报备请求（仅 active 状态可改）。"""

    contact_person: Optional[str] = Field(None, max_length=50)
    contact_phone: Optional[str] = Field(None, max_length=20)
    opportunity_source: Optional[str] = Field(None, max_length=50)

    expected_amount: Optional[Decimal] = Field(None, ge=0)
    follow_up_notes: Optional[str] = None
    last_follow_up_at: Optional[datetime] = None

    notes: Optional[str] = None
    updated_by: Optional[int] = None


# ---------------------------------------------------------------------------
# 释放
# ---------------------------------------------------------------------------


class ReleaseClaimReq(BaseModel):
    """主动释放报备请求（status=released）。"""

    release_reason: Optional[str] = Field(
        None, max_length=200, description="释放原因：误报/客户拒绝/商机移交/..."
    )
    updated_by: Optional[int] = None


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class LeadClaimResp(BaseModel):
    """报备响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int

    partner_id: Optional[int] = None
    company_id: Optional[int] = None

    claim_date: datetime
    protection_days: int
    expire_at: Optional[datetime] = None

    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    opportunity_source: Optional[str] = None

    expected_amount: Optional[Decimal] = None
    follow_up_notes: Optional[str] = None
    last_follow_up_at: Optional[datetime] = None

    status: str
    release_reason: Optional[str] = None
    released_at: Optional[datetime] = None

    notes: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None
    updated_by: Optional[int] = None


class LeadClaimListResp(BaseModel):
    """报备分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[LeadClaimResp]


class LeadClaimStatsResp(BaseModel):
    """报备统计概览。

    - 各状态计数
    - 按 partner 分组（按 status=active 的报备归到 partner；partner_id=NULL 归到 unknown）
    """

    total: int
    active: int
    expired: int
    won: int
    lost: int
    released: int
    by_partner: dict[str, int] = Field(
        default_factory=dict,
        description="按渠道/销售 ID 聚合的 active 报备数（key=partner_id 字符串；'unknown' 表示无 partner）",
    )


class LeadClaimConflictResp(BaseModel):
    """冲突查询响应（按 company_id 返回该公司所有报备 + active 计数）。"""

    company_id: int
    total: int
    active_count: int
    items: List[LeadClaimResp] = Field(
        default_factory=list,
        description="该企业的所有报备（含 active/expired/won/lost/released 全状态）",
    )


__all__ = [
    "LeadClaimConflictResp",
    "LeadClaimCreateReq",
    "LeadClaimListResp",
    "LeadClaimResp",
    "LeadClaimStatsResp",
    "LeadClaimUpdateReq",
    "ReleaseClaimReq",
]
