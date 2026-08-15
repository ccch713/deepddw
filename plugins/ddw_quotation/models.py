"""DDW 报价单插件 ORM 模型。

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
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import Base, TenantMixin, TimestampMixin

# BigInteger 在 SQLite 不支持 -> 退化到 Integer
BigInt = BigInteger().with_variant(Integer(), "sqlite")


class Quotation(Base, TenantMixin, TimestampMixin):
    """报价单主表。"""

    __tablename__ = "crm_quotations"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("crm_contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    opportunity_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("crm_opportunities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    quotation_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(200))
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    discount_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), default=Decimal("100"))
    final_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    terms: Mapped[Optional[str]] = mapped_column(Text)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Quotation id={self.id} no={self.quotation_no!r}>"


class QuotationItem(Base):
    """报价单明细行。"""

    __tablename__ = "crm_quotation_items"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    quotation_id: Mapped[int] = mapped_column(
        BigInt, ForeignKey("crm_quotations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_name: Mapped[str] = mapped_column(String(200), nullable=False)
    product_type: Mapped[Optional[str]] = mapped_column(String(30))
    product_code: Mapped[Optional[str]] = mapped_column(String(50))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit: Mapped[str] = mapped_column(String(20), default="套")
    unit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    description: Mapped[Optional[str]] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self) -> str:  # pragma: no cover
        return f"<QuotationItem id={self.id} product={self.product_name!r}>"


__all__ = ["Quotation", "QuotationItem"]
