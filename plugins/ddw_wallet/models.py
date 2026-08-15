"""ddw_wallet ORM 模型 — 6 张表，表前缀 dw_wallet_。

所有金额字段：Integer（单位：分），禁止 Float。
SQLAlchemy 2.0 Mapped 风格。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)


class WalletBase(DeclarativeBase):
    """钱包插件独立 Base（不依赖平台租户体系）。"""
    pass


class WalletAccount(WalletBase):
    """钱包账户 — 每个学生/作者一个余额账户（三钱包）。"""
    __tablename__ = "dw_wallet_accounts"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    user_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # G7 多租户
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_tenant_user"),)
    # 三钱包（分：Integer，禁 Float）
    recharge_balance_cents: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )  # 实收→消费
    income_balance_cents: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )  # 可提现→兜底
    skin_balance_cents: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )  # 虚拟币，不可提现
    frozen_cents: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default="active", nullable=False
    )  # active|frozen|closed
    version: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )


class RechargeOrder(WalletBase):
    """充值单 — 用户发起充值产生的订单。"""
    __tablename__ = "dw_wallet_recharge_orders"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    order_no: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # G7 多租户
    amount_cents: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # wechat|alipay
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False
    )  # pending|paid|failed|refunded
    provider_order_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    notify_raw: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    paid_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


class ChargeRecord(WalletBase):
    """扣费流水 — 按量扣费记录。"""
    __tablename__ = "dw_wallet_charge_records"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    txn_no: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # G7 多租户
    amount_cents: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    charge_type: Mapped[str] = mapped_column(
        String(24), nullable=False
    )  # study_time|courseware|voice
    subject: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )
    ref_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )  # 幂等键
    ref_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # session|generation|other
    balance_after: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


class RefundRecord(WalletBase):
    """退款记录 — 余额原路退回。"""
    __tablename__ = "dw_wallet_refund_records"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    refund_no: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # G7 多租户
    amount_cents: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # wechat|alipay
    source: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # recharge|balance
    status: Mapped[str] = mapped_column(
        String(16), default="processing", nullable=False
    )  # processing|success|failed
    provider_refund_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


class RoyaltyRecord(WalletBase):
    """分成记录 — 课件作者收益。"""
    __tablename__ = "dw_wallet_royalty_records"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    royalty_no: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False
    )
    author_user_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # G7 多租户
    courseware_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )
    trigger_txn_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )  # 防重复分成
    study_amount_cents: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    rate_percent: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # 80 或 50
    income_cents: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), default="settled", nullable=False
    )  # settled|pending
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


class RateRule(WalletBase):
    """计费规则 — 可配置的单价表。"""
    __tablename__ = "dw_wallet_rate_rules"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    charge_type: Mapped[str] = mapped_column(
        String(24), nullable=False
    )  # study_time|courseware|voice
    subject: Mapped[Optional[str]] = mapped_column(
        nullable=True
    )  # None=默认
    unit_price_cents: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    unit: Mapped[str] = mapped_column(
        String(16), default="minute", nullable=False
    )  # minute|item|second
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )


class Ledger(WalletBase):
    """余额流水 — 任何余额变动（credit/debit/freeze/unfreeze）必须写入。

    幂等键：ref_id UNIQUE（与 charge_records.ref_id 同一约束）。
    可回溯：余额快照 balance_after + balance_type。
    """
    __tablename__ = "dw_wallet_ledger"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    txn_no: Mapped[str] = mapped_column(
        String(40), unique=True, nullable=False
    )  # 流水号（自动生成）
    user_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )  # G7 多租户
    direction: Mapped[str] = mapped_column(
        String(4), nullable=False
    )  # in|out
    amount_cents: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    balance_type: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # recharge|income|skin
    ref_id: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )  # 幂等键
    ref_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # recharge|charge|refund|royalty|freeze|unfreeze|adjust
    balance_after: Mapped[int] = mapped_column(
        Integer, nullable=False
    )  # 变动后该钱包余额快照
    reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )




class AuditLog(WalletBase):
    """审计日志 — 余额变更记录（G12）。"""
    __tablename__ = "dw_wallet_audit_logs"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    operator: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # system/admin/<user_id>
    action: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # manual_credit/manual_debit/adjust/freeze/refund
    amount_cents: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    balance_before: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    balance_after: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


class TenantPaymentConfig(WalletBase):
    """租户支付配置 — 子商户号路由（G10）。"""
    __tablename__ = "dw_wallet_tenant_payment_config"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False
    )
    wechat_mch_id: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True
    )
    wechat_app_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    alipay_app_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    wechat_cert_path: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True
    )  # 证书路径（不存密钥值）
    wechat_key_path: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


class RawCallback(WalletBase):
    """原始回调 — 异步队列（G11）。"""
    __tablename__ = "dw_wallet_raw_callbacks"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # wechat|alipay
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # payment|refund
    raw_body: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    headers: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # 请求头（微信验签需要）
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False
    )  # pending/processed/failed
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        nullable=True
    )


class WithdrawRequest(WalletBase):
    """提现申请 — income 余额提现（G15）。"""
    __tablename__ = "dw_wallet_withdraw_requests"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    tenant_id: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(64), index=True, nullable=False
    )
    amount_cents: Mapped[int] = mapped_column(
        Integer, nullable=False
    )
    channel: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # wechat|alipay
    status: Mapped[str] = mapped_column(
        String(16), default="pending", nullable=False
    )  # pending/approved/rejected/processing/success/failed
    reject_reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )



__all__ = [
    "ChargeRecord",
    "Ledger",
    "AuditLog",
    "TenantPaymentConfig",
    "RawCallback",
    "WithdrawRequest",
    "RateRule",
    "RechargeOrder",
    "RefundRecord",
    "RoyaltyRecord",
    "WalletAccount",
    "WalletBase",
]
