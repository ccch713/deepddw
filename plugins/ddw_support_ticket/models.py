"""DDW 售后工单插件 ORM 模型。

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
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import Base, TenantMixin, TimestampMixin

# BigInteger 在 SQLite 不支持 -> 退化到 Integer
BigInt = BigInteger().with_variant(Integer(), "sqlite")


class SupportTicket(Base, TenantMixin, TimestampMixin):
    """售后工单主表（客户报修 / 咨询 / 投诉）。"""

    __tablename__ = "crm_support_tickets"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)

    # ---- 关联 ----
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInt,
        ForeignKey("crm_companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    instance_id: Mapped[Optional[int]] = mapped_column(
        BigInt,
        ForeignKey("crm_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ---- 编号 / 标题 ----
    ticket_no: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    # ---- 分类 / 优先级 ----
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # bug / question / feature / billing / training
    priority: Mapped[str] = mapped_column(
        String(20), default="normal", nullable=False, index=True
    )  # low / normal / high / urgent

    # ---- 描述 / 解决 ----
    description: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_to: Mapped[Optional[int]] = mapped_column(BigInt, index=True, nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ---- 状态 / 时间 ----
    status: Mapped[str] = mapped_column(
        String(20), default="open", nullable=False, index=True
    )  # open / in_progress / pending / resolved / closed / cancelled
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ---- 审计 ----
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SupportTicket id={self.id} no={self.ticket_no!r} status={self.status}>"


__all__ = ["SupportTicket"]
