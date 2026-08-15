"""ddw_wallet Pydantic v2 请求/响应模型（三钱包版本）。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# ── 请求 ──────────────────────────────────────────────


class RechargeCreate(BaseModel):
    """创建充值单。"""
    amount_cents: int = Field(ge=100, le=1000000)
    channel: Literal["wechat", "alipay"]
    user_id: str = Field(min_length=1, max_length=64)


class ChargeCreate(BaseModel):
    """按量扣费。"""
    user_id: str
    charge_type: Literal["study_time", "courseware", "voice"]
    subject: Optional[str] = None
    ref_id: str
    ref_type: str = "session"
    amount_cents: int = Field(gt=0)
    balance_priority: Optional[str] = "recharge,income,skin"


class RefundCreate(BaseModel):
    """余额退款。"""
    user_id: str
    amount_cents: int = Field(gt=0)
    source: Literal["recharge", "income", "skin"] = "recharge"


class RoyaltyCreate(BaseModel):
    """课件分成入账。"""
    author_user_id: str
    courseware_id: str
    trigger_txn_id: str
    study_amount_cents: int
    subject: Optional[str] = None


class FreezeRequest(BaseModel):
    """冻结/解冻请求。"""
    amount_cents: int = Field(gt=0)
    reason: str = ""


class WithdrawCreate(BaseModel):
    """提现申请。"""
    user_id: str
    amount_cents: int = Field(gt=0)
    channel: Literal["wechat", "alipay"] = "wechat"


class ReconcileRequest(BaseModel):
    """对账请求。"""
    date: str  # YYYY-MM-DD


# ── 响应 ──────────────────────────────────────────────


class WalletAccountOut(BaseModel):
    user_id: str
    tenant_id: str = "default"
    recharge_balance_cents: int = 0
    income_balance_cents: int = 0
    skin_balance_cents: int = 0
    frozen_cents: int = 0
    status: str = "active"
    updated_at: Optional[datetime] = None


class RechargeOut(BaseModel):
    order_no: str
    amount_cents: int
    channel: str
    status: str
    pay_params: Optional[dict] = None


class ChargeOut(BaseModel):
    txn_no: str
    amount_cents: int
    balance_after: int


class RefundOut(BaseModel):
    refund_no: str
    status: str


class RoyaltyOut(BaseModel):
    royalty_no: str
    income_cents: int


class TransactionOut(BaseModel):
    txn_no: Optional[str] = None
    order_no: Optional[str] = None
    amount_cents: int
    direction: Literal["in", "out"]
    channel: str
    subject: Optional[str] = None
    created_at: datetime


class PaginatedTransactions(BaseModel):
    items: list[TransactionOut]
    total: int
    page: int
    size: int


class RateRuleOut(BaseModel):
    id: int
    charge_type: str
    subject: Optional[str]
    unit_price_cents: int
    unit: str
    active: bool


class PlatformAccountOut(BaseModel):
    total_fee_cents: int
    count: int


class WithdrawOut(BaseModel):
    withdraw_no: str
    amount_cents: int
    status: str


__all__ = [
    "ChargeCreate",
    "ChargeOut",
    "FreezeRequest",
    "PaginatedTransactions",
    "PlatformAccountOut",
    "RateRuleOut",
    "RechargeCreate",
    "RechargeOut",
    "ReconcileRequest",
    "RefundCreate",
    "RefundOut",
    "RoyaltyCreate",
    "RoyaltyOut",
    "TransactionOut",
    "WalletAccountOut",
    "WithdrawCreate",
    "WithdrawOut",
]
