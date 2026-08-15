"""DDW AI Hub 核心 ORM 模型（v5.4）。

集中所有跨插件/全局的表结构。
- :class:`Tenant` — 租户
- :class:`User` — 用户
- :class:`TokenQuota` — 租户级 Token 配额
- :class:`ApiKey` — API Key
- :class:`TrainingSession` — 培训会话（供培训插件引用）
- :class:`TrainingAssessment` — 培训考核结果

注意：所有租户级业务表都继承 :class:`TenantMixin`，由 :mod:`core.database.tenant_filter`
自动注入/过滤 tenant_id。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.session import Base
from core.database.tenant_filter import TENANT_AWARE_ATTR

# BigInteger 在 SQLite 不支持 AUTOINCREMENT → 退化到 Integer（保留 PG 上的 BigInt）
BigInt = BigInteger().with_variant(Integer(), "sqlite")


class TenantMixin:
    """租户感知基类。子类的 mapper 自动注册 __tenant_aware__ = True。"""

    tenant_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # 标记 mapper 为租户感知
    __tenant_aware__ = True  # type: ignore[assignment]


class TimestampMixin:
    """时间戳混入。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# 租户 / 用户 / 配额 / Key
# ---------------------------------------------------------------------------


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="free", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    users: Mapped[list["User"]] = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    quotas: Mapped[list["TokenQuota"]] = relationship("TokenQuota", back_populates="tenant", cascade="all, delete-orphan")
    api_keys: Mapped[list["ApiKey"]] = relationship("ApiKey", back_populates="tenant", cascade="all, delete-orphan")


class User(Base, TenantMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        # 同手机号可跨租户存在（经销商在多个客户租户/经销商租户都有账号）
        UniqueConstraint("phone", "tenant_id", name="uq_users_phone_tenant"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    role: Mapped[str] = mapped_column(String(30), default="member", nullable=False)  # owner/admin/member
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 超管账号强制设备验证（红线）
    device_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # 允许设备指纹列表（JSON：serial/screen_resolution 等）
    device_allowlist: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # 账号锁定截止时间（L3 限流写入）
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 密码最后修改时间（密码过期判断依据）
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 邮箱绑定
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")


class TokenQuota(Base, TenantMixin, TimestampMixin):
    __tablename__ = "token_quotas"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    period: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)  # monthly/daily
    token_limit: Mapped[int] = mapped_column(BigInt, default=100_000, nullable=False)
    tokens_used: Mapped[int] = mapped_column(BigInt, default=0, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    period_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="quotas")


class ApiKey(Base, TenantMixin, TimestampMixin):
    __tablename__ = "api_keys"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="api_keys")


# ---------------------------------------------------------------------------
# 培训相关（供 ddw-training 插件使用）
# ---------------------------------------------------------------------------


class TrainingSession(Base, TenantMixin, TimestampMixin):
    __tablename__ = "training_sessions"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    session_uuid: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # 内存会话 sid 桥接
    user_id: Mapped[int] = mapped_column(BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(40), nullable=False)  # physics/chemistry
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_sec: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    moves_completed: Mapped[str] = mapped_column(Text, default="", nullable=False)  # "1,2,3,4"
    final_scores: Mapped[str] = mapped_column(Text, default="{}", nullable=False)  # JSON: 4 维评分
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)


class TrainingAssessment(Base, TenantMixin, TimestampMixin):
    __tablename__ = "training_assessments"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[Optional[int]] = mapped_column(BigInt, ForeignKey("training_sessions.id", ondelete="SET NULL"), nullable=True)
    subject: Mapped[str] = mapped_column(String(40), nullable=False)
    overall_score: Mapped[float] = mapped_column(Integer, default=0, nullable=False)
    conceptual_clarity: Mapped[float] = mapped_column(Integer, default=0, nullable=False)
    reasoning_depth: Mapped[float] = mapped_column(Integer, default=0, nullable=False)
    engagement_quality: Mapped[float] = mapped_column(Integer, default=0, nullable=False)
    pedagogical_alignment: Mapped[float] = mapped_column(Integer, default=0, nullable=False)
    grade: Mapped[str] = mapped_column(String(10), default="C", nullable=False)  # A/B/C/D
    details_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)


class UserBinding(Base, TenantMixin, TimestampMixin):
    __tablename__ = "user_bindings"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # wechat/dingtalk/github
    provider_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    binding_type: Mapped[str] = mapped_column(String(32), default="login", nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class LoginAudit(Base):
    """登录审计日志（全局，不按租户隔离）。"""
    __tablename__ = "login_audit"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True, index=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    method: Mapped[str] = mapped_column(String(20), default="password", nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fail_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False, index=True)


class KnowledgeBase(Base, TimestampMixin):
    """知识库（2026-08-09 新增，core/knowledge.py 持久化用）。"""
    __tablename__ = "kb_bases"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)


class KnowledgeBasePermission(Base):
    """知识库权限矩阵（2026-08-09 新增，按 tenant 隔离）。"""
    __tablename__ = "kb_base_permissions"
    __table_args__ = (
        UniqueConstraint("base_id", "tenant_id", name="uq_kb_perm_base_tenant"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_id: Mapped[int] = mapped_column(Integer, ForeignKey("kb_bases.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    permissions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class ChannelPartner(Base, TimestampMixin):
    """渠道商（PRD §14 — channel partner accounts）。"""

    __tablename__ = "channel_partners"
    __table_args__ = ({"extend_existing": True},)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("channel_partners.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[str] = mapped_column(String(16), default="small", nullable=False)  # big / small
    commission_balance_cny: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    contact: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class WhitelistEntry(Base, TimestampMixin, TenantMixin):
    """白名单（PRD §13 — phone numbers that can register for a tenant）。"""

    __tablename__ = "whitelist_entries"
    __table_args__ = (
        UniqueConstraint("phone", "tenant_id", name="uq_whitelist_phone_tenant"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    phone: Mapped[str] = mapped_column(String(191), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    added_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)


# 显式声明，让 tenant_filter 白名单生效
__all__ = [
    "TENANT_AWARE_ATTR",
    "ApiKey",
    "ChannelPartner",
    "KnowledgeBase",
    "KnowledgeBasePermission",
    "LoginAudit",
    "Tenant",
    "TenantMixin",
    "TimestampMixin",
    "TokenQuota",
    "TrainingAssessment",
    "TrainingSession",
    "User",
    "UserBinding",
    "WhitelistEntry",
]
