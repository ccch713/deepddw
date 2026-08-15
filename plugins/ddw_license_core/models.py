"""DDW 许可证核心插件 ORM 模型。

继承 DDW 平台核心：
- core.database.session.Base: DeclarativeBase 根
- core.database.models.TenantMixin: 自动注入 tenant_id + 标记租户感知
- core.database.models.TimestampMixin: 自动注入 created_at / updated_at
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import Base, TenantMixin, TimestampMixin

# BigInteger 在 SQLite 不支持 -> 退化到 Integer
BigInt = BigInteger().with_variant(Integer(), "sqlite")


class License(Base, TenantMixin, TimestampMixin):
    """许可证主表（按企业签发，记录可用产品 / 插件 / 容量）。"""

    __tablename__ = "crm_licenses"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)

    # ---- 关联企业 ----
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInt,
        ForeignKey("crm_companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ---- 编号 / 类型 ----
    license_no: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    license_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # commercial / trial / education / partner / oem

    # ---- 授权范围 ----
    product_ids: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # 元素为 crm_products.id
    plugin_entitlements: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # 元素形如 {"plugin": "ddw-llm-gateway", "max_users": 5}

    # ---- 容量 ----
    max_users: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    max_nodes: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # ---- 有效期 ----
    valid_from: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    valid_to: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # ---- 状态 / 备注 ----
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False, index=True
    )  # active / expired / revoked / suspended
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ---- 续费链 ----
    parent_license_id: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True, index=True)
    renewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ---- 审计 ----
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<License id={self.id} no={self.license_no!r} type={self.license_type}>"


__all__ = ["License"]
