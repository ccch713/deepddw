"""DDW Member VIP - 数据模型."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

LEVELS = ("normal", "silver", "gold", "diamond")
TX_TYPES = ("recharge", "consume", "gift", "refund")

VIP_LEVELS = {
    "normal": {"min_recharge": 0, "discount": 1.0, "benefits": "基础服务"},
    "silver": {"min_recharge": 500, "discount": 0.95, "benefits": "95折 + 免费洗牙1次/年"},
    "gold": {"min_recharge": 2000, "discount": 0.90, "benefits": "9折 + 免费洗牙2次/年 + 优先预约"},
    "diamond": {"min_recharge": 5000, "discount": 0.85, "benefits": "85折 + 免费洗牙+涂氟 + 专属客服"},
}

RECHARGE_GIFTS = {
    500: 50,
    1000: 150,
    2000: 400,
    3000: 700,
    5000: 1500,
}


class MemberAccount(BaseModel):
    id: Optional[str] = None
    patient_id: str
    level: str = "normal"
    balance: float = 0.0
    total_recharged: float = 0.0
    total_consumed: float = 0.0
    discount_rate: float = 1.0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MemberAccountCreate(BaseModel):
    patient_id: str


class RechargeRequest(BaseModel):
    amount: float
    description: Optional[str] = None


class ConsumeRequest(BaseModel):
    amount: float
    description: Optional[str] = None


class Transaction(BaseModel):
    id: Optional[str] = None
    account_id: str
    type: str  # recharge/consume/gift/refund
    amount: float
    balance_after: float
    description: Optional[str] = None
    created_at: Optional[datetime] = None


class AccountList(BaseModel):
    total: int
    accounts: list[MemberAccount]


class TransactionList(BaseModel):
    total: int
    transactions: list[Transaction]


class LevelStat(BaseModel):
    count: int
    balance: float


class StatsResponse(BaseModel):
    total_accounts: int
    total_balance: float
    total_recharged: float
    total_consumed: float
    level_distribution: dict[str, LevelStat]


class HealthResponse(BaseModel):
    plugin: str = "ddw_member_vip"
    version: str = "0.1.0"
    status: str = "ok"
    total_accounts: int = 0
