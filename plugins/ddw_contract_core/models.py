"""DDW 合同核心插件 ORM 模型。

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


class Contract(Base, TenantMixin, TimestampMixin):
    """合同主表。"""

    __tablename__ = "crm_contracts"
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
    quotation_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("crm_quotations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contract_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(200))
    contract_type: Mapped[str] = mapped_column(
        String(30), default="standard", nullable=False, index=True
    )
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    signed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    payment_terms: Mapped[Optional[str]] = mapped_column(Text)
    deliverables: Mapped[Optional[str]] = mapped_column(Text)
    sla: Mapped[Optional[str]] = mapped_column(Text)
    attachments: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # 审批 / 终止原因（审计字段；spec §5 简版未列出，但 services._contract_to_dict
    # 序列化层与状态机需要，因此按 broken 备份回填）
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    terminated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    terminate_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Contract id={self.id} no={self.contract_no!r}>"


__all__ = ["Contract"]
