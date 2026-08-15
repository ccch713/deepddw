"""DDW 企业主体管理插件 ORM 模型。

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
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import Base, TenantMixin, TimestampMixin

# BigInteger 在 SQLite 不支持 -> 退化到 Integer
BigInt = BigInteger().with_variant(Integer(), "sqlite")


class Company(Base, TenantMixin, TimestampMixin):
    """企业主体主表。"""

    __tablename__ = "crm_companies"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)

    # 工商信息
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    credit_code: Mapped[Optional[str]] = mapped_column(String(18), unique=True, index=True)
    short_name: Mapped[Optional[str]] = mapped_column(String(100))
    company_type: Mapped[Optional[str]] = mapped_column(String(50))
    registered_address: Mapped[Optional[str]] = mapped_column(String(500))
    legal_representative: Mapped[Optional[str]] = mapped_column(String(50))
    established_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    business_license_url: Mapped[Optional[str]] = mapped_column(String(500))
    business_scope: Mapped[Optional[str]] = mapped_column(Text)

    # 认证状态
    certification_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    certification_submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    certification_approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    certification_expires_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # 开票信息
    invoice_title: Mapped[Optional[str]] = mapped_column(String(200))
    tax_id: Mapped[Optional[str]] = mapped_column(String(20))
    bank_name: Mapped[Optional[str]] = mapped_column(String(100))
    bank_account: Mapped[Optional[str]] = mapped_column(String(50))
    company_phone: Mapped[Optional[str]] = mapped_column(String(30))
    company_address: Mapped[Optional[str]] = mapped_column(String(500))

    # 业务字段
    industry: Mapped[Optional[str]] = mapped_column(String(50))
    company_size: Mapped[Optional[str]] = mapped_column(String(20))
    registered_capital: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    annual_revenue: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))

    # 扩展
    tags: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)

    # 审计
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Company id={self.id} name={self.name!r}>"


__all__ = ["Company"]
