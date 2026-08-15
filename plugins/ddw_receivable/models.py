"""DDW 应收账款插件 ORM 模型。

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


class Receivable(Base, TenantMixin, TimestampMixin):
    """应收账款主表。"""

    __tablename__ = "crm_receivables"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("crm_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contract_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("crm_contracts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    plan_name: Mapped[Optional[str]] = mapped_column(String(100))
    node_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )
    due_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Receivable id={self.id} amount={self.amount} status={self.status!r}>"


__all__ = ["Receivable"]
