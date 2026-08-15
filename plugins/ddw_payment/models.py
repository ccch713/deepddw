"""DDW Payment - 数据模型.

包含两层模型：
- SQLAlchemy ORM :class:`Payment` — 实收主表（供 finance_dashboard / reconciliation 等跨插件查询）
- Pydantic 模型 — 供 PaymentStore (SQLite) 路由层使用
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import BigInteger, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import Base, TenantMixin, TimestampMixin

# BigInteger 在 SQLite 不支持 -> 退化到 Integer
BigInt = BigInteger().with_variant(Integer(), "sqlite")


# ---------------------------------------------------------------------------
# SQLAlchemy ORM 模型（crm_payments 表）
# ---------------------------------------------------------------------------


class Payment(Base, TenantMixin, TimestampMixin):
    """实收主表。"""

    __tablename__ = "crm_payments"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)

    company_id: Mapped[Optional[int]] = mapped_column(
        BigInt,
        ForeignKey("crm_companies.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
        index=True,
    )

    payment_no: Mapped[str] = mapped_column(
        String(30), unique=True, index=True, nullable=False
    )
    payer_name: Mapped[str] = mapped_column(String(200), nullable=False)

    bank_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bank_account: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    matched_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0"), nullable=False
    )

    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Payment id={self.id} no={self.payment_no!r} amount={self.amount} status={self.status!r}>"


# ---------------------------------------------------------------------------
# Pydantic 模型（供 PaymentStore / 路由层使用）
# ---------------------------------------------------------------------------

PAYMENT_METHODS = ("cash", "wechat", "alipay", "card", "member")
STATUSES = ("pending", "paid", "refunded")


class PaymentItem(BaseModel):
    item_name: str
    quantity: int = 1
    unit_price: float
    subtotal: float
    treatment_type: Optional[str] = None


class PaymentRecord(BaseModel):
    id: Optional[str] = None
    patient_id: str
    doctor_id: str
    items: list[PaymentItem]
    total_amount: float
    discount_amount: float = 0.0
    actual_amount: float
    payment_method: str
    status: str = "pending"
    paid_at: Optional[datetime] = None
    receipt_number: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None


class PaymentCreate(BaseModel):
    patient_id: str
    doctor_id: str
    items: list[PaymentItem]
    discount_amount: float = 0.0
    payment_method: str = "wechat"
    notes: Optional[str] = None


class PaymentUpdate(BaseModel):
    status: Optional[str] = None
    payment_method: Optional[str] = None
    paid_at: Optional[datetime] = None
    notes: Optional[str] = None


class PaymentList(BaseModel):
    total: int
    records: list[PaymentRecord]


class RefundRequest(BaseModel):
    refund_amount: Optional[float] = None
    reason: Optional[str] = None


class DailySummary(BaseModel):
    date: str
    total_income: float
    by_method: dict[str, float]
    transaction_count: int
    refund_count: int
    refund_amount: float


class HealthResponse(BaseModel):
    plugin: str = "ddw_payment"
    version: str = "0.1.0"
    status: str = "ok"
    total_records: int = 0
