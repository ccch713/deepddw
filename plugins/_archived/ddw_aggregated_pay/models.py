"""DDW Aggregated Pay - 数据模型."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

TX_STATUSES = ("pending", "success", "failed", "closed")


class PayChannel(BaseModel):
    id: Optional[str] = None
    channel_name: str  # wechat_pay / alipay / unionpay / cash
    is_active: bool = True
    config: dict[str, str] = Field(default_factory=dict)


class PayChannelCreate(BaseModel):
    channel_name: str
    is_active: bool = True
    config: dict[str, str] = Field(default_factory=dict)


class PayTransaction(BaseModel):
    id: Optional[str] = None
    payment_record_id: str
    channel: str
    amount: float
    trade_no: Optional[str] = None
    status: str = "pending"
    reconciled: bool = False
    created_at: Optional[datetime] = None


class PayTransactionCreate(BaseModel):
    payment_record_id: str
    channel: str
    amount: float
    trade_no: Optional[str] = None


class PayTransactionUpdate(BaseModel):
    status: Optional[str] = None
    trade_no: Optional[str] = None
    reconciled: Optional[bool] = None


class ChannelList(BaseModel):
    total: int
    channels: list[PayChannel]


class TransactionList(BaseModel):
    total: int
    transactions: list[PayTransaction]


class MismatchedItem(BaseModel):
    payment_record_id: str
    reason: str


class ReconcileReport(BaseModel):
    date: str
    matched: int
    mismatched: list[MismatchedItem]
    payment_total: float
    transaction_total: float
    diff: float


class HealthResponse(BaseModel):
    plugin: str = "ddw_aggregated_pay"
    version: str = "0.1.0"
    status: str = "ok"
    total_channels: int = 0
    total_transactions: int = 0
