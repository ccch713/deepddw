"""DDW 销售机会插件 ORM 模型。

继承 DDW 平台核心：
- core.database.session.Base: DeclarativeBase 根
- core.database.models.TenantMixin: 自动注入 tenant_id + 标记租户感知
- core.database.models.TimestampMixin: 自动注入 created_at / updated_at
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import Base, TenantMixin, TimestampMixin

# BigInteger 在 SQLite 不支持 -> 退化到 Integer
BigInt = BigInteger().with_variant(Integer(), "sqlite")


class Opportunity(Base, TenantMixin, TimestampMixin):
    """销售机会主表。"""

    __tablename__ = "crm_opportunities"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("crm_contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    source: Mapped[Optional[str]] = mapped_column(String(50))
    owner_id: Mapped[Optional[int]] = mapped_column(BigInt, index=True)
    estimated_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    stage: Mapped[str] = mapped_column(
        String(30), default="initial_contact", nullable=False, index=True
    )
    probability: Mapped[int] = mapped_column(Integer, default=10)
    expected_close_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False, index=True)
    won_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    lost_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Opportunity id={self.id} name={self.name!r} stage={self.stage!r}>"


__all__ = ["Opportunity"]
