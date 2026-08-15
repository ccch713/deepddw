"""DDW 人员资质插件 ORM 模型。

两张核心表：
- personnel_certs   — 证书主表（增删改查 + 统计）
- cert_renewals     — 年检记录（独立表，支持多次年检历史）

所有租户级表继承 :class:`TenantMixin`，由 :mod:`core.database.tenant_filter` 自动注入/过滤 tenant_id。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database.session import Base
from core.database.tenant_filter import TENANT_AWARE_ATTR

# 兼容 SQLite（BigInteger -> Integer）
BigInt = Integer()


class PersonnelCert(Base):
    """人员证书主表。"""

    __tablename__ = "personnel_certs"
    __table_args__ = {"extend_existing": True}
    __tenant_aware__ = True  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    person_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    person_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 工号
    cert_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    cert_no: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    cert_level: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 一级/二级/三级
    issue_org: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    issue_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    renewal_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # 下次年检
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class CertRenewal(Base):
    """年检记录。"""

    __tablename__ = "cert_renewals"
    __table_args__ = {"extend_existing": True}
    __tenant_aware__ = True  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    cert_id: Mapped[int] = mapped_column(Integer, ForeignKey("personnel_certs.id", ondelete="CASCADE"), nullable=False, index=True)
    renewal_date: Mapped[date] = mapped_column(Date, nullable=False)
    result: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 通过/未通过/待审
    operator: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending/passed/failed
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class CertAlert(Base):
    """提醒通知（独立于邮件/IM，可被前端轮询）。"""

    __tablename__ = "cert_alerts"
    __table_args__ = {"extend_existing": True}
    __tenant_aware__ = True  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    cert_id: Mapped[int] = mapped_column(Integer, ForeignKey("personnel_certs.id", ondelete="CASCADE"), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)  # expiry_30/expiry_60/expiry_90/renewal_due
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)  # info/warn/critical
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0/1
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


__all__ = [
    "TENANT_AWARE_ATTR",
    "CertAlert",
    "CertRenewal",
    "PersonnelCert",
]
