"""DDW 发票插件 ORM 模型。

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


class Invoice(Base, TenantMixin, TimestampMixin):
    """发票主表。"""

    __tablename__ = "crm_invoices"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_id: Mapped[Optional[int]] = mapped_column(
        BigInt, ForeignKey("crm_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    invoice_no: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    invoice_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    invoice_title: Mapped[str] = mapped_column(String(200), nullable=False)
    tax_id: Mapped[str] = mapped_column(String(20), nullable=False)
    invoice_url: Mapped[Optional[str]] = mapped_column(String(500))
    issued_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="requested", nullable=False, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    # ---- 通知追踪 (Task 1) ----
    notified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notification_method: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # email / sms / none

    # ---- 下载追踪 (Task 1) ----
    download_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_downloaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_downloaded_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    # ---- 发票文件扩展信息 (Task 1) ----
    invoice_code: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # 发票代码（电子发票 10-12 位）
    invoice_check_code: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # 发票校验码（电子发票后 6 位）
    file_type: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True
    )  # pdf / ofd / xml
    file_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Invoice id={self.id} type={self.invoice_type!r} total={self.total_amount}>"


__all__ = ["Invoice"]
