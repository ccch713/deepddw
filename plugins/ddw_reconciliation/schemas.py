from __future__ import annotations

from typing import List, Optional

"""DDW 应收实收核销插件 Pydantic schemas。

包含：
- MatchReq / MatchSuggestionItem / MatchResp：自动匹配推荐
- ConfirmReq / ConfirmMatchItem / ConfirmResp：确认核销
- CancelReq / CancelResp：取消核销
- HistoryItem / HistoryResp：核销历史（内存 list）
- UnmatchedPaymentItem / UnmatchedReceivableItem / UnmatchedSummaryResp：未核销汇总
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# 1. 匹配推荐
# ---------------------------------------------------------------------------


class MatchReq(BaseModel):
    """自动匹配推荐请求。"""

    payment_id: int = Field(..., ge=1, description="实收单 ID（crm_payments.id）")


class MatchSuggestionItem(BaseModel):
    """单条匹配建议。"""

    receivable_id: int = Field(..., description="应收 ID（crm_receivables.id）")
    node_name: str = Field(..., description="应收节点名称")
    company_id: Optional[int] = Field(None, description="关联企业 ID")
    amount: Decimal = Field(..., description="应收总金额 amount")
    paid_amount: Decimal = Field(..., description="已收金额 paid_amount")
    outstanding_amount: Decimal = Field(..., description="剩余未收 = amount - paid_amount")
    due_date: date = Field(..., description="应收日期")
    status: str = Field(..., description="应收当前状态")

    # ---- 匹配元信息 ----
    match_type: str = Field(..., description="匹配类型：exact（金额+公司完全相等）")
    suggested_amount: Decimal = Field(..., description="建议核销金额")
    confidence: float = Field(..., ge=0, le=1, description="匹配置信度（exact=1.0）")


class MatchResp(BaseModel):
    """自动匹配推荐响应。"""

    payment_id: int
    payment_no: Optional[str] = Field(None, description="实收单号（PAY-YYYYMMDD-NNN）")
    payment_amount: Decimal
    payment_matched_amount: Decimal
    payment_remaining: Decimal = Field(..., description="payment.amount - payment.matched_amount")
    payment_company_id: Optional[int] = None
    payment_status: str
    suggestions: List[MatchSuggestionItem] = Field(..., description="匹配建议列表（已按 confidence 降序）")


# ---------------------------------------------------------------------------
# 2. 确认核销
# ---------------------------------------------------------------------------


class ConfirmMatchItem(BaseModel):
    """单条核销明细：把 payment 的一笔钱分配到某个 receivable。"""

    receivable_id: int = Field(..., ge=1, description="应收 ID")
    amount: Decimal = Field(..., gt=0, description="本次分配到该应收的金额（>0）")


class ConfirmReq(BaseModel):
    """确认核销请求。"""

    payment_id: int = Field(..., ge=1, description="实收单 ID")
    matches: List[ConfirmMatchItem] = Field(..., min_length=1, description="分配明细（至少 1 条）")


class ConfirmResultItem(BaseModel):
    """单条核销结果（被更新的应收 + 本次匹配金额）。"""

    receivable_id: int
    paid_amount: Decimal
    outstanding_amount: Decimal
    status: str
    matched_this_time: Decimal = Field(..., description="本次核销到该应收的金额")


class ConfirmResp(BaseModel):
    """确认核销响应。"""

    payment_id: int
    payment_no: Optional[str] = None
    payment_status: str
    payment_matched_amount: Decimal
    payment_remaining: Decimal
    total_matched: Decimal = Field(..., description="本次 confirm 累计分配金额")
    results: List[ConfirmResultItem]
    history_id: int = Field(..., description="本次操作在内存历史中的序号")


# ---------------------------------------------------------------------------
# 3. 取消核销
# ---------------------------------------------------------------------------


class CancelReq(BaseModel):
    """取消核销请求。

    两种模式（二选一）：
    - 取消单条 (payment_id, receivable_id)
    - 整笔 payment 全部回退 cancel_all=True
    """

    payment_id: int = Field(..., ge=1, description="实收单 ID")
    receivable_id: Optional[int] = Field(
        None, ge=1, description="应收 ID；与 cancel_all 互斥"
    )
    cancel_all: bool = Field(
        False, description="True 表示把该 payment 上的所有核销一次性回退"
    )


class CancelResultItem(BaseModel):
    """单条取消结果。"""

    receivable_id: int
    reversed_amount: Decimal = Field(..., description="本次回退金额")
    paid_amount: Decimal
    outstanding_amount: Decimal
    status: str


class CancelResp(BaseModel):
    """取消核销响应。"""

    payment_id: int
    payment_no: Optional[str] = None
    payment_status: str
    payment_matched_amount: Decimal
    total_reversed: Decimal
    results: List[CancelResultItem]
    history_id: int


# ---------------------------------------------------------------------------
# 4. 核销历史
# ---------------------------------------------------------------------------


class HistoryItem(BaseModel):
    """单条核销历史。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: int = Field(..., description="内存序号（自增）")
    action: str = Field(..., description="动作：confirm / cancel")
    payment_id: int
    receivable_id: Optional[int] = Field(None, description="NULL 表示 cancel_all")
    amount: Decimal = Field(..., description="本次操作涉及的金额")
    timestamp: datetime

    # before / after 状态（用于审计）
    payment_status_before: str
    payment_status_after: str
    payment_matched_before: Decimal
    payment_matched_after: Decimal

    receivable_status_before: Optional[str] = Field(None, description="receivable 不参与时为 NULL")
    receivable_status_after: Optional[str] = None
    receivable_paid_before: Optional[Decimal] = None
    receivable_paid_after: Optional[Decimal] = None


class HistoryResp(BaseModel):
    """核销历史响应（按 id 倒序）。"""

    total: int
    items: List[HistoryItem]


# ---------------------------------------------------------------------------
# 5. 未核销汇总
# ---------------------------------------------------------------------------


class UnmatchedPaymentItem(BaseModel):
    """未核销实收条目。"""

    id: int
    payment_no: str
    payer_name: str
    company_id: Optional[int] = None
    amount: Decimal
    matched_amount: Decimal
    unmatched_amount: Decimal = Field(..., description="未核销 = amount - matched_amount")
    status: str
    payment_date: date


class UnmatchedReceivableItem(BaseModel):
    """未收齐应收条目。"""

    id: int
    node_name: str
    company_id: Optional[int] = None
    order_id: Optional[int] = None
    amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal = Field(..., description="未收 = amount - paid_amount")
    status: str
    due_date: date


class UnmatchedSummaryResp(BaseModel):
    """未核销汇总。"""

    payment_count: int
    receivable_count: int
    payment_unmatched_total: Decimal = Field(Decimal(0), description="未核销实收金额合计")
    receivable_outstanding_total: Decimal = Field(Decimal(0), description="未收应收金额合计")
    payments: List[UnmatchedPaymentItem]
    receivables: List[UnmatchedReceivableItem]


__all__ = [
    "CancelReq",
    "CancelResp",
    "CancelResultItem",
    "ConfirmMatchItem",
    "ConfirmReq",
    "ConfirmResp",
    "ConfirmResultItem",
    "HistoryItem",
    "HistoryResp",
    "MatchReq",
    "MatchResp",
    "MatchSuggestionItem",
    "UnmatchedPaymentItem",
    "UnmatchedReceivableItem",
    "UnmatchedSummaryResp",
]
