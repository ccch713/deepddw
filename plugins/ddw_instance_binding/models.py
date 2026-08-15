"""DDW 实例绑定插件 ORM 模型。

继承 DDW 平台核心：
- core.database.session.Base: DeclarativeBase 根
- core.database.models.TenantMixin: 自动注入 tenant_id + 标记租户感知
- core.database.models.TimestampMixin: 自动注入 created_at / updated_at
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import Base, TenantMixin, TimestampMixin

# BigInteger 在 SQLite 不支持 -> 退化到 Integer
BigInt = BigInteger().with_variant(Integer(), "sqlite")


class Instance(Base, TenantMixin, TimestampMixin):
    """客户侧部署实例（每张许可证可绑定多个实例：边缘节点 / 中心节点 / 备份）。"""

    __tablename__ = "crm_instances"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)

    # ---- 关联 ----
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInt,
        ForeignKey("crm_companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    license_id: Mapped[Optional[int]] = mapped_column(
        BigInt,
        ForeignKey("crm_licenses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ---- 实例标识 ----
    instance_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # center / edge / backup / dev / test
    instance_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    instance_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ---- 指纹 / 环境 ----
    fingerprint: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    environment: Mapped[str] = mapped_column(
        String(20), default="production", nullable=False, index=True
    )  # production / staging / dev / test
    endpoint: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ---- 状态 / 心跳 ----
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False, index=True
    )  # active / offline / revoked / replaced
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    # ---- 审计 ----
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Instance id={self.id} type={self.instance_type} env={self.environment}>"


__all__ = ["Instance"]
