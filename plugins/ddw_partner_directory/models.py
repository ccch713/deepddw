"""DDW 经销商开户插件 ORM 模型。

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
    Boolean,
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


class PartnerDemoAccount(Base, TenantMixin, TimestampMixin):
    """经销商名下客户的 demo 账号清单（存在经销商租户内）。

    用途：经销商登录后查看名下所有客户的演示版登录账号/密码，方便带客户体验。
    安全边界：demo 账号 ≠ 生产账号；生产环境账号由客户内部管理员管理，
    经销商无权查看/登录生产环境。
    """

    __tablename__ = "partner_demo_accounts"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)

    # ---- 客户信息 ----
    client_tenant_id: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True, index=True)
    client_name: Mapped[str] = mapped_column(String(200), nullable=False)
    client_industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ---- demo 登录信息 ----
    demo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    demo_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    demo_password: Mapped[str] = mapped_column(String(128), nullable=False)
    demo_note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ---- 状态 ----
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active/expired/disabled
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Partner(Base, TenantMixin, TimestampMixin):
    """经销商主表（reseller / agent / distributor）。"""

    __tablename__ = "crm_partners"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)

    # ---- 关联（可空：允许未挂靠企业的独立经销商） ----
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInt,
        ForeignKey("crm_companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ---- 分类 ----
    partner_type: Mapped[str] = mapped_column(
        String(30), default="reseller", nullable=False, index=True
    )  # reseller / agent / distributor
    level: Mapped[str] = mapped_column(
        String(20), default="normal", nullable=False, index=True
    )  # normal / silver / gold / strategic

    # ---- 区域 / 行业 ----
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ---- 可售范围 / 折扣（百分数：80 = 8 折） ----
    allowed_products: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    product_discount: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("80"), nullable=False
    )
    plugin_discount: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("85"), nullable=False
    )
    service_discount: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("90"), nullable=False
    )

    # ---- 合作期 ----
    agreement_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    agreement_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # ---- 联系人 ----
    contact_person: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # ---- 状态 / 备注 ----
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False, index=True
    )  # active / inactive / suspended
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ---- 审计 ----
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Partner id={self.id} type={self.partner_type} level={self.level}>"


__all__ = ["Partner"]
