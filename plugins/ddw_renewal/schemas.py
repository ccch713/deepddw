from __future__ import annotations

from typing import List, Optional

"""DDW 续费与预警插件 Pydantic schemas。

约定：
- 所有响应 schema 都包含 ``tenant_id: int = Field(1, ge=1)``，与其它 P0-1~P4-5 保持一致
- ``tenant_id`` 在开发模式下硬编码 default=1，生产从 token 取
- 金额字段统一为 ``Decimal``，避免 float 精度漂移
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 通用 tenant mixin
# ---------------------------------------------------------------------------


class _TenantMixin(BaseModel):
    """所有响应都携带租户 ID。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")


# ---------------------------------------------------------------------------
# 1. Expiring（即将到期）
# ---------------------------------------------------------------------------


class ExpiringItem(BaseModel):
    """单条即将到期的许可证。"""

    id: int = Field(..., description="许可证 ID")
    license_no: str = Field(..., description="许可证单号")
    license_type: str = Field(..., description="许可证类型（trial / formal / renewal）")
    status: str = Field(..., description="当前状态")
    company_id: Optional[int] = Field(None, description="关联企业 ID（可能为 NULL）")
    company_name: Optional[str] = Field(None, description="关联企业名称（LEFT JOIN，可能为 NULL）")
    product_ids: List[int] = Field(default_factory=list, description="授权产品 ID 列表")
    plugin_entitlements: List[str] = Field(default_factory=list, description="授权插件清单")
    max_users: int = Field(0, description="最大用户数")
    max_nodes: int = Field(0, description="最大节点数")
    valid_from: date = Field(..., description="生效起始日期")
    valid_to: date = Field(..., description="生效截止日期")
    days_remaining: int = Field(..., description="距到期天数（≥0；负数表示已逾期，expiring 不应出现）")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")


class ExpiringResp(_TenantMixin):
    """即将到期许可证响应。"""

    window_days: int = Field(..., description="到期窗口（天），30 / 60 / 90")
    today: date = Field(..., description="查询基准日期（UTC 当天）")
    total: int = Field(..., description="即将到期许可证总数")
    items: List[ExpiringItem] = Field(..., description="按 valid_to 升序的许可证列表")


# ---------------------------------------------------------------------------
# 2. Overdue（已逾期）
# ---------------------------------------------------------------------------


class OverdueItem(BaseModel):
    """单条已逾期的许可证。"""

    id: int = Field(..., description="许可证 ID")
    license_no: str = Field(..., description="许可证单号")
    license_type: str = Field(..., description="许可证类型")
    status: str = Field(..., description="当前状态（active 表示已逾期但未自动标记 / expired 已自动标记）")
    company_id: Optional[int] = Field(None, description="关联企业 ID")
    company_name: Optional[str] = Field(None, description="关联企业名称（LEFT JOIN）")
    valid_from: date = Field(..., description="生效起始日期")
    valid_to: date = Field(..., description="生效截止日期")
    days_overdue: int = Field(..., description="已逾期天数（≥1）")
    parent_license_id: Optional[int] = Field(None, description="续费关系中父许可证 ID（NULL=从未续费）")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")


class OverdueResp(_TenantMixin):
    """已逾期许可证响应。"""

    today: date = Field(..., description="查询基准日期")
    total: int = Field(..., description="已逾期许可证总数")
    items: List[OverdueItem] = Field(..., description="按 valid_to 升序的逾期列表（最早逾期的在最前）")


# ---------------------------------------------------------------------------
# 3. Quote（续费报价）
# ---------------------------------------------------------------------------


class QuoteReq(BaseModel):
    """续费报价请求（POST body）。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")
    license_id: int = Field(..., ge=1, description="待续费的目标许可证 ID")
    renewal_unit_days: Optional[int] = Field(
        None,
        ge=1,
        le=3650,
        description="续费时长（天）。None 时优先用上次 license 时长，否则用 default_renewal_unit_days",
    )


class QuoteBreakdown(BaseModel):
    """续费报价明细。"""

    historical_unit_price: Optional[Decimal] = Field(
        None, description="历史合同单日单价（CNY/天），无历史时为 None"
    )
    historical_contract_id: Optional[int] = Field(None, description="历史合同 ID（最近一张同 company 的 active 合同）")
    historical_contract_no: Optional[str] = Field(None, description="历史合同单号")
    historical_contract_total: Optional[Decimal] = Field(None, description="历史合同总金额")
    historical_contract_days: Optional[int] = Field(None, description="历史合同有效天数")
    renewal_unit_days: int = Field(..., description="本次续费时长（天）")
    estimated_unit_price: Decimal = Field(..., description="本次使用的单日单价（CNY/天），无历史时为 0")
    fallback_used: bool = Field(
        False, description="是否使用兜底单价（无历史合同 → 0 元/天，仅作占位）"
    )


class QuoteResp(_TenantMixin):
    """续费报价响应。"""

    license_id: int = Field(..., description="待续费的许可证 ID")
    license_no: str = Field(..., description="待续费的许可证单号")
    license_type: str = Field(..., description="许可证类型")
    company_id: Optional[int] = Field(None, description="关联企业 ID")
    company_name: Optional[str] = Field(None, description="关联企业名称")
    valid_from: date = Field(..., description="现许可证生效起始日")
    valid_to: date = Field(..., description="现许可证生效截止日（续费起点）")
    estimated_amount: Decimal = Field(..., description="估算续费金额（CNY）")
    currency: str = Field("CNY", description="币种")
    breakdown: QuoteBreakdown = Field(..., description="报价明细")


# ---------------------------------------------------------------------------
# 4. Stats（续费统计概览）
# ---------------------------------------------------------------------------


class RenewalStatsBucket(BaseModel):
    """单个到期窗口的统计。"""

    window_days: int = Field(..., description="窗口大小（30 / 60 / 90）")
    expiring: int = Field(..., description="该窗口内 active 且即将到期的许可证数")
    total_users: int = Field(..., description="这些许可证授权用户数合计")
    total_nodes: int = Field(..., description="这些许可证授权节点数合计")


class RenewalStatsResp(_TenantMixin):
    """续费统计概览响应。"""

    today: date = Field(..., description="查询基准日期")
    active: int = Field(..., description="当前 active 状态的许可证总数")
    overdue: int = Field(..., description="已逾期许可证数")
    renewed_total: int = Field(..., description="历史已续费许可证数（status=renewed）")
    # 续费率 = renewed_total / (renewed_total + expired_total)，保留 4 位小数
    renewal_rate: float = Field(..., description="续费率 = renewed / (renewed + expired)")
    # 30/60/90 三个窗口
    windows: List[RenewalStatsBucket] = Field(..., description="各窗口到期统计")
    # 汇总字段
    expiring_30: int = Field(..., description="30 天内到期（兼容字段）")
    expiring_60: int = Field(..., description="60 天内到期（兼容字段）")
    expiring_90: int = Field(..., description="90 天内到期（兼容字段）")
    total_users_at_risk: int = Field(..., description="90 天内到期许可证授权用户数合计")
    total_nodes_at_risk: int = Field(..., description="90 天内到期许可证授权节点数合计")


__all__ = [
    "ExpiringItem",
    "ExpiringResp",
    "OverdueItem",
    "OverdueResp",
    "QuoteBreakdown",
    "QuoteReq",
    "QuoteResp",
    "RenewalStatsBucket",
    "RenewalStatsResp",
]
