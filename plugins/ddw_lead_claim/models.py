"""DDW 线索抢单保护插件 ORM 模型。

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
    BigInteger,
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


class LeadClaim(Base, TenantMixin, TimestampMixin):
    """线索抢单保护记录（经销商对某企业线索的抢单 / 报备 / 保护）。"""

    __tablename__ = "crm_lead_claims"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)

    # ---- 关联 ----
    partner_id: Mapped[Optional[int]] = mapped_column(
        BigInt,
        ForeignKey("crm_partners.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInt,
        ForeignKey("crm_companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ---- 抢单时间 / 保护期 ----
    claim_date: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    protection_days: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    # ---- 联系信息 ----
    contact_person: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # ---- 商机信息 ----
    opportunity_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    expected_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)

    # ---- 跟进 ----
    follow_up_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_follow_up_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ---- 状态 / 备注 ----
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False, index=True
    )  # active / expired / released / converted
    release_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ---- 审计 ----
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LeadClaim id={self.id} partner_id={self.partner_id} status={self.status}>"


__all__ = ["LeadClaim"]
