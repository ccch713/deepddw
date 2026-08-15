"""DDW 产品目录插件 ORM 模型。

继承 DDW 平台核心：
- core.database.session.Base: DeclarativeBase 根
- core.database.models.TenantMixin: 自动注入 tenant_id + 标记租户感知
- core.database.models.TimestampMixin: 自动注入 created_at / updated_at
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import Base, TenantMixin, TimestampMixin

# BigInteger 在 SQLite 不支持 -> 退化到 Integer
BigInt = BigInteger().with_variant(Integer(), "sqlite")


class Product(Base, TenantMixin, TimestampMixin):
    """产品目录主表（许可证 / 插件 / 服务的可售 SKU）。"""

    __tablename__ = "crm_products"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)

    # ---- 基础 ----
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    product_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # license / plugin / service / support / training
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ---- 价格 / 计量 ----
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), default="套/年", nullable=False)
    # 套/年 / 次 / 人天 / 月 / 年

    # ---- 版本 / 启用 ----
    version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # ---- 扩展属性（按 product_type 不同可放技术规格 / 服务范围） ----
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # ---- 审计 ----
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Product id={self.id} code={self.code!r} type={self.product_type}>"


__all__ = ["Product"]
