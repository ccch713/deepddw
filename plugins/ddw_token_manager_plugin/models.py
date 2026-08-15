"""
SQLAlchemy 数据模型 — Token 额度管理

对应 One API 源码映射:
- TokenQuota  → model/token.go:Token (L23-37)
- ConsumeLog  → model/log.go:Log (L15-32)
- CalibrationRecord → DDW 独有
- SubscriptionInfo → DDW 独有
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类

    [v5.7修复] SDK 当前未提供统一 ORM Base，暂用本地定义。
    待 SDK 新增 sdk.orm_base 后迁移。
    """
    pass


# ── Token 额度模型 ──────────────────────────────────────────────


class TokenStatus(enum.IntEnum):
    """
    令牌状态枚举

    对应 model/token.go:L17-21
    """
    ENABLED = 1       # 不使用 0，0 是默认值
    DISABLED = 2      # 同样不使用 0
    EXPIRED = 3
    EXHAUSTED = 4


class TokenQuota(Base):
    """
    令牌额度表

    映射: model/token.go:Token (L23-37)
    每个令牌绑定一个用户，拥有独立的额度池。
    unlimited_quota=True 时跳过 Token 级别额度检查。
    """
    __tablename__ = "token_quotas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(48), unique=True, index=True, nullable=False)
    status: Mapped[int] = mapped_column(Integer, default=TokenStatus.ENABLED, nullable=False)
    name: Mapped[str] = mapped_column(String(255), index=True, default="", nullable=False)
    created_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    accessed_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expired_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # -1 → 永不过期（映射 model/token.go:ExpiredTime default:-1）
    # 用 nullable + negative-infinity 语义模拟
    remain_quota: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    unlimited_quota: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    used_quota: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    models: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 逗号分隔的允许模型列表
    subnet: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    def __repr__(self) -> str:
        return f"<TokenQuota id={self.id} user_id={self.user_id} remain={self.remain_quota}>"


# ── 消费日志 ─────────────────────────────────────────────────────


class ConsumeLog(Base):
    """
    消费日志表

    映射: model/log.go:Log (L15-32)
    记录每次 API 调用的 token 消耗和 quota 花费。
    """
    __tablename__ = "consume_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    token_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    model: Mapped[str] = mapped_column(String(255), index=True, default="", nullable=False)
    token_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quota_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)  # 倍率公式
    is_stream: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    elapsed_time: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 毫秒
    system_prompt_reset: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    request_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    __table_args__ = (
        Index("ix_consume_logs_user_model", "user_id", "model"),
    )

    def __repr__(self) -> str:
        return f"<ConsumeLog id={self.id} model={self.model} quota={self.quota_cost}>"


# ── 校准记录（DDW 独有）──────────────────────────────────────────


class CalibrationRecord(Base):
    """
    校准记录表 — DDW 差异化核心

    One API 没有此功能。DDW 需要基于 Provider 实际账单
    反算校准系数 K，修正本地计费与 Provider 实际扣费的偏差。
    """
    __tablename__ = "calibration_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    estimated_cost: Mapped[float] = mapped_column(Float, nullable=False)  # 本地估算费用(美元)
    actual_cost: Mapped[float] = mapped_column(Float, nullable=False)    # Provider实际扣费(美元)
    ratio_adjustment: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)  # 校准系数 K
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (
        Index("ix_calibration_provider_time", "provider", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<CalibrationRecord provider={self.provider} K={self.ratio_adjustment:.4f}>"


# ── 订阅信息（DDW 独有）──────────────────────────────────────────


class SubscriptionInfo(Base):
    """
    订阅信息表 — DDW 独有

    企业客户登记订阅信息，支持基于订阅状态的智能路由。
    """
    __tablename__ = "subscription_infos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    plan_name: Mapped[str] = mapped_column(String(128), nullable=False)
    total_quota: Mapped[float] = mapped_column(Float, nullable=False)   # 总额度（美元或积分）
    used_quota: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    @property
    def remaining(self) -> float:
        """剩余额度"""
        return self.total_quota - self.used_quota

    @property
    def usage_ratio(self) -> float:
        """使用比例 (0.0 ~ 1.0)"""
        if self.total_quota <= 0:
            return 1.0
        return min(self.used_quota / self.total_quota, 1.0)

    def __repr__(self) -> str:
        return f"<SubscriptionInfo provider={self.provider} plan={self.plan_name} remaining={self.remaining:.2f}>"
