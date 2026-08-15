"""DDW 订单插件 ORM 模型。

继承 DDW 平台核心：
- core.database.session.Base: DeclarativeBase 根
- core.database.models.TenantMixin: 自动注入 tenant_id + 标记租户感知
- core.database.models.TimestampMixin: 自动注入 created_at / updated_at
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
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


class Order(Base, TenantMixin, TimestampMixin):
    """订单主表。"""

    __tablename__ = "crm_orders"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contract_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("crm_contracts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(200))
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    items: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    cancel_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Order id={self.id} no={self.order_no!r}>"


__all__ = ["Order"]
