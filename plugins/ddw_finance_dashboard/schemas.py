from __future__ import annotations

"""DDW 财务看板插件 Pydantic schemas。

本插件为只读聚合查询，因此 schemas 全部为响应类型，不含 Create/Update 请求。
所有 schema 都包含 ``tenant_id: int`` 以保持与 P1-1 / P1-3 / P1-4 一致的多租户约定。
"""

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 通用 tenant 字段（参考 P1-1 / P1-3 / P1-4 约定）
# ---------------------------------------------------------------------------


class _TenantMixin(BaseModel):
    """所有 dashboard 响应都携带租户 ID。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")


# ---------------------------------------------------------------------------
# 1. Overview（财务总览）
# ---------------------------------------------------------------------------


class OverviewResp(_TenantMixin):
    """财务总览：合同 / 应收 / 实收 / 逾期 四维度概览。"""

    # ---- 合同总览 ----
    contracts_total: int = Field(..., description="合同总数")
    contracts_signed: int = Field(..., description="已签合同数（status in signed/active/completed）")
    contracts_total_amount: Decimal = Field(Decimal("0"), description="合同总金额")
    contracts_signed_amount: Decimal = Field(Decimal("0"), description="已签合同总金额")

    # ---- 应收总览 ----
    receivables_total: int = Field(..., description="应收记录总数")
    receivables_total_amount: Decimal = Field(Decimal("0"), description="应收总金额")
    receivables_paid_amount: Decimal = Field(Decimal("0"), description="应收已收金额")
    receivables_outstanding_amount: Decimal = Field(
        Decimal("0"), description="应收未收金额 = total - paid"
    )

    # ---- 实收总览 ----
    payments_total: int = Field(..., description="实收记录总数")
    payments_total_amount: Decimal = Field(Decimal("0"), description="实收总金额")
    payments_matched_amount: Decimal = Field(Decimal("0"), description="已核销金额")
    payments_unmatched_amount: Decimal = Field(
        Decimal("0"), description="未核销金额 = total - matched"
    )

    # ---- 逾期 ----
    overdue_count: int = Field(..., description="逾期应收条数")
    overdue_amount: Decimal = Field(Decimal("0"), description="逾期应收的未收金额合计")


# ---------------------------------------------------------------------------
# 2. Overdue（逾期列表）
# ---------------------------------------------------------------------------


class OverdueItem(BaseModel):
    """单条逾期应收（含企业名 + 未收金额计算字段）。"""

    id: int
    tenant_id: int
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    contract_id: Optional[int] = None
    node_name: str
    amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal = Field(..., description="未收金额 = amount - paid_amount")
    due_date: date
    status: str


class OverdueResp(_TenantMixin):
    """逾期列表响应。"""

    total: int = Field(..., description="当前返回条数")
    total_overdue_amount: Decimal = Field(Decimal("0"), description="逾期未收金额合计")
    items: List[OverdueItem] = Field(..., description="按未收金额降序的逾期应收")


# ---------------------------------------------------------------------------
# 3. Trend（最近 N 月趋势）
# ---------------------------------------------------------------------------


class TrendItem(BaseModel):
    """单月趋势数据。"""

    month: str = Field(..., description="月份，格式 YYYY-MM")
    receivable_amount: Decimal = Field(Decimal("0"), description="当月应收金额（按 due_date）")
    payment_amount: Decimal = Field(Decimal("0"), description="当月实收金额（按 payment_date）")
    net: Decimal = Field(Decimal("0"), description="差额 = receivable - payment")


class TrendResp(_TenantMixin):
    """趋势响应（按月升序，月份连续无空洞）。"""

    months: int = Field(..., description="回看月数")
    items: List[TrendItem] = Field(..., description="按月统计序列")


# ---------------------------------------------------------------------------
# 4. Stats（按状态分布 + 按企业未收金额）
# ---------------------------------------------------------------------------


class StatsResp(_TenantMixin):
    """财务统计响应。"""

    # ---- 按合同状态分布（计数 + 金额） ----
    contracts_by_status: Dict[str, int] = Field(
        default_factory=dict, description="合同按状态计数（draft/pending_approval/approved/signed/...）"
    )
    contracts_amount_by_status: Dict[str, Decimal] = Field(
        default_factory=dict, description="合同按状态金额汇总"
    )

    # ---- 按应收状态分布 ----
    receivables_by_status: Dict[str, int] = Field(
        default_factory=dict, description="应收按状态计数（pending/partial/paid/overdue）"
    )
    receivables_amount_by_status: Dict[str, Decimal] = Field(
        default_factory=dict, description="应收按状态金额汇总（amount 列）"
    )
    receivables_outstanding_by_status: Dict[str, Decimal] = Field(
        default_factory=dict, description="应收按状态未收金额 = amount - paid_amount"
    )

    # ---- 按实收状态分布 ----
    payments_by_status: Dict[str, int] = Field(
        default_factory=dict, description="实收按状态计数（pending/partial/matched/unmatched）"
    )
    payments_amount_by_status: Dict[str, Decimal] = Field(
        default_factory=dict, description="实收按状态金额汇总"
    )

    # ---- 按企业未收金额 ----
    receivables_outstanding_by_company: List["OutstandingByCompanyItem"] = Field(
        default_factory=list, description="按企业未收金额汇总（top 50）"
    )


class OutstandingByCompanyItem(BaseModel):
    """按企业未收金额条目。"""

    company_id: Optional[int] = None
    company_name: Optional[str] = None
    outstanding_amount: Decimal = Field(..., description="该企业未收金额合计")
    receivable_count: int = Field(..., description="该企业未收应收条数")


__all__ = [
    "OutstandingByCompanyItem",
    "OverdueItem",
    "OverdueResp",
    "OverviewResp",
    "StatsResp",
    "TrendItem",
    "TrendResp",
]
