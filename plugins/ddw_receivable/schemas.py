from __future__ import annotations

"""DDW 应收管理插件 Pydantic schemas。

包含：
- ReceivableCreateReq：新建应收（必填 node_name/amount/due_date）
- ReceivableUpdateReq：更新应收（仅 pending/overdue 可改）
- RecordPaymentReq：记录收款（increment 模式：传本次收款金额）
- ReceivableResp：应收响应
- ReceivableListResp：分页列表
- ReceivableStatsResp：统计概览
- ReceivableOverdueListResp：逾期列表
"""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------


class ReceivableCreateReq(BaseModel):
    """新建应收请求。"""

    tenant_id: int = Field(1, ge=1, description="租户 ID（开发模式硬编码，生产从 token 取）")

    company_id: Optional[int] = Field(None, description="关联客户企业 ID")
    order_id: Optional[int] = Field(None, description="关联订单 ID")
    contract_id: Optional[int] = Field(None, description="关联合同 ID")

    plan_name: Optional[str] = Field(
        None, max_length=100, description="应收计划名称（如 2026 智造项目）"
    )
    node_name: str = Field(
        ..., min_length=1, max_length=100, description="节点名称：首款/部署款/验收款/续费款"
    )
    amount: Decimal = Field(..., gt=0, description="应收金额（>0）")
    due_date: date = Field(..., description="应收日期")
    notes: Optional[str] = None
    created_by: Optional[int] = Field(None, description="创建人 ID")


# ---------------------------------------------------------------------------
# 更新
# ---------------------------------------------------------------------------


class ReceivableUpdateReq(BaseModel):
    """更新应收请求（全字段可选；仅 pending/overdue 状态可改）。"""

    plan_name: Optional[str] = Field(None, max_length=100)
    node_name: Optional[str] = Field(None, min_length=1, max_length=100)
    amount: Optional[Decimal] = Field(None, gt=0)
    due_date: Optional[date] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# 收款（增量模式）
# ---------------------------------------------------------------------------


class RecordPaymentReq(BaseModel):
    """记录收款请求（增量模式：传本次收款金额，累加到 paid_amount）。"""

    payment_amount: Decimal = Field(
        ..., gt=0, description="本次收款金额（>0；最终 paid_amount 允许超过 amount）"
    )
    payment_date: Optional[datetime] = Field(
        None, description="实收时间；不传则默认 now(UTC)"
    )


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------


class ReceivableResp(BaseModel):
    """应收响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int

    company_id: Optional[int] = None
    order_id: Optional[int] = None
    contract_id: Optional[int] = None

    plan_name: Optional[str] = None
    node_name: str

    amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal = Field(..., description="未收金额 = amount - paid_amount")

    due_date: date
    paid_at: Optional[datetime] = None

    status: str
    notes: Optional[str] = None

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[int] = None


class ReceivableListResp(BaseModel):
    """应收分页列表响应。"""

    total: int
    page: int
    page_size: int
    items: List[ReceivableResp]


# ---------------------------------------------------------------------------
# 统计 / 逾期
# ---------------------------------------------------------------------------


class ReceivableStatsResp(BaseModel):
    """应收统计概览。"""

    total: int
    pending: int
    partial: int
    paid: int
    overdue: int

    total_amount: Decimal = Field(Decimal("0"), description="所有应收 amount 之和")
    paid_amount: Decimal = Field(Decimal("0"), description="所有已收 paid_amount 之和")
    outstanding_amount: Decimal = Field(
        Decimal("0"), description="未收金额合计 = sum(amount) - sum(paid_amount)"
    )


class ReceivableOverdueListResp(BaseModel):
    """逾期列表响应（含总金额）。"""

    total: int
    items: List[ReceivableResp]
    total_overdue_amount: Decimal = Field(Decimal("0"), description="逾期金额合计")
    total_outstanding_amount: Decimal = Field(
        Decimal("0"), description="逾期未收金额合计"
    )


__all__ = [
    "ReceivableCreateReq",
    "ReceivableListResp",
    "ReceivableOverdueListResp",
    "ReceivableResp",
    "ReceivableStatsResp",
    "ReceivableUpdateReq",
    "RecordPaymentReq",
]
