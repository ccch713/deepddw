"""DDW 销售记录插件 ORM 模型。

继承 DDW 平台核心：
- core.database.session.Base: DeclarativeBase 根
- core.database.models.TenantMixin: 自动注入 tenant_id + 标记租户感知
- core.database.models.TimestampMixin: 自动注入 created_at / updated_at
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
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


class SalesNote(Base, TenantMixin, TimestampMixin):
    """销售记录（走访 / 沟通 / 跟进 / 备忘）。"""

    __tablename__ = "crm_sales_notes"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)

    # ---- 关联 ----
    user_id: Mapped[Optional[int]] = mapped_column(BigInt, index=True, nullable=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInt,
        ForeignKey("crm_companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    contact_id: Mapped[Optional[int]] = mapped_column(
        BigInt,
        ForeignKey("crm_contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    opportunity_id: Mapped[Optional[int]] = mapped_column(
        BigInt,
        ForeignKey("crm_opportunities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ---- 业务字段 ----
    note_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # visit / call / meeting / follow_up / memo
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    visit_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    # ---- 标签 / 附件 ----
    tags: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    attachments: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    # ---- 审计 ----
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<SalesNote id={self.id} type={self.note_type}>"


__all__ = ["SalesNote"]
