from __future__ import annotations

"""DDW 销售看板插件 Pydantic schemas。

本插件为只读聚合查询，因此 schemas 全部为响应类型，不含 Create/Update 请求。
所有 schema 都包含 ``tenant_id: int`` 以保持与 P0-1~P0-4 一致的多租户约定。
"""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 通用 tenant 字段（参考 P0-1~P0-4 约定）
# ---------------------------------------------------------------------------


class _TenantMixin(BaseModel):
    """所有 dashboard 响应都携带租户 ID。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")


# ---------------------------------------------------------------------------
# 1. Overview（总览）
# ---------------------------------------------------------------------------


class OverviewResp(_TenantMixin):
    """销售总览。"""

    companies: int = Field(..., description="企业总数")
    contacts: int = Field(..., description="联系人总数")
    opportunities: int = Field(..., description="商机总数（含 open / won / lost / closed）")
    quotations: int = Field(..., description="报价单总数")
    estimated_amount: Decimal = Field(..., description="进行中（status=open）商机预计金额总和")
    won_amount: Decimal = Field(..., description="成交金额（status=won 的 estimated_amount 之和）")
    won_customers: int = Field(..., description="成交客户数（去重后的 company_id 数）")
    # 业务语义补充字段（与 P0-3 stats 对齐）
    open_opportunities: int = Field(0, description="进行中商机数（status=open）")
    won_opportunities: int = Field(0, description="成交商机数（status=won）")
    lost_opportunities: int = Field(0, description="丢单商机数（status=lost）")
    accepted_quotations: int = Field(0, description="已接受报价单数")
    accepted_amount: Decimal = Field(Decimal("0"), description="已接受报价单的 final_amount 之和")


# ---------------------------------------------------------------------------
# 2. Funnel（漏斗）
# ---------------------------------------------------------------------------


class FunnelItem(BaseModel):
    """单阶段漏斗数据。"""

    stage: str = Field(..., description="商机阶段编码")
    stage_label: str = Field("", description="商机阶段中文标签")
    count: int = Field(..., description="该阶段商机数")
    total_amount: Decimal = Field(..., description="该阶段预计金额总和")


class FunnelResp(_TenantMixin):
    """漏斗响应（按 STAGE_DISPLAY_ORDER 顺序）。"""

    stages: List[FunnelItem] = Field(..., description="各阶段数据")
    total: int = Field(..., description="所有阶段商机总数")
    total_amount: Decimal = Field(..., description="所有阶段预计金额总和")


# ---------------------------------------------------------------------------
# 3. Trend（最近 12 月趋势）
# ---------------------------------------------------------------------------


class TrendItem(BaseModel):
    """单月趋势数据。"""

    month: str = Field(..., description="月份，格式 YYYY-MM")
    new_opportunities: int = Field(..., description="当月新增商机数")
    total_amount: Decimal = Field(..., description="当月新增商机的预计金额总和")
    won_amount: Decimal = Field(..., description="当月成交的商机金额（按 won_at 归属月份）")


class TrendResp(_TenantMixin):
    """趋势响应（按月升序，月份连续无空洞）。"""

    months: int = Field(..., description="回看月数")
    items: List[TrendItem] = Field(..., description="按月统计序列")


# ---------------------------------------------------------------------------
# 4. Ranking（销售排行）
# ---------------------------------------------------------------------------


class RankingItem(BaseModel):
    """单个 owner 的排行数据。"""

    owner_id: int = Field(..., description="负责人用户 ID")
    total_opportunities: int = Field(..., description="名下商机总数")
    estimated_amount: Decimal = Field(..., description="名下商机预计金额总和")
    won_amount: Decimal = Field(..., description="名下成交金额（status=won）")
    won_count: int = Field(..., description="名下成交商机数")
    lost_count: int = Field(..., description="名下丢单商机数")
    win_rate: float = Field(..., description="成交率 = won_count / (won_count + lost_count)，仅含终止态")


class RankingResp(_TenantMixin):
    """销售排行响应（按 estimated_amount 降序）。"""

    items: List[RankingItem] = Field(..., description="按 estimated_amount 降序的排行")
    total_owners: int = Field(..., description="上榜 owner 数")


# ---------------------------------------------------------------------------
# 5. Recent（最近商机）
# ---------------------------------------------------------------------------


class RecentOpportunityItem(BaseModel):
    """最近商机条目。"""

    id: int
    name: str
    stage: str
    stage_label: str = ""
    status: str
    estimated_amount: Optional[Decimal] = None
    owner_id: Optional[int] = None
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    expected_close_date: Optional[str] = None
    updated_at: Optional[datetime] = None
    won_at: Optional[datetime] = None


class RecentOpportunityResp(_TenantMixin):
    """最近商机列表。"""

    limit: int = Field(..., description="返回条数上限")
    items: List[RecentOpportunityItem] = Field(..., description="按 updated_at 倒序的商机列表")


# ---------------------------------------------------------------------------
# 6. Stage Distribution（阶段分布，饼图用）
# ---------------------------------------------------------------------------


class StageDistributionItem(BaseModel):
    """单阶段分布数据（用于前端饼图 / 环图）。"""

    stage: str = Field(..., description="阶段编码")
    stage_label: str = Field("", description="阶段中文标签")
    count: int = Field(..., description="该阶段商机数")
    amount: Decimal = Field(..., description="该阶段预计金额")


class StageDistributionResp(_TenantMixin):
    """阶段分布响应。"""

    items: List[StageDistributionItem] = Field(..., description="按 STAGE_DISPLAY_ORDER 顺序输出")
    total_count: int = Field(..., description="所有阶段商机总数")
    total_amount: Decimal = Field(..., description="所有阶段预计金额总和")


__all__ = [
    "FunnelItem",
    "FunnelResp",
    "OverviewResp",
    "RankingItem",
    "RankingResp",
    "RecentOpportunityItem",
    "RecentOpportunityResp",
    "StageDistributionItem",
    "StageDistributionResp",
    "TrendItem",
    "TrendResp",
]
