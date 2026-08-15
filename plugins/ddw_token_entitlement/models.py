"""DDW Token 配额与凭据插件 ORM 模型。

继承 DDW 平台核心：
- core.database.session.Base: DeclarativeBase 根
- core.database.models.TenantMixin: 自动注入 tenant_id + 标记租户感知
- core.database.models.TimestampMixin: 自动注入 created_at / updated_at
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import Base, TenantMixin, TimestampMixin

# BigInteger 在 SQLite 不支持 -> 退化到 Integer
BigInt = BigInteger().with_variant(Integer(), "sqlite")


class TokenEntitlement(Base, TenantMixin, TimestampMixin):
    """Token 配额与凭据（按企业 / 实例分配 LLM 调用额度）。"""

    __tablename__ = "crm_token_entitlements"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)

    # ---- 关联 ----
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInt,
        ForeignKey("crm_companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    instance_id: Mapped[Optional[int]] = mapped_column(
        BigInt,
        ForeignKey("crm_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ---- 类型 ----
    entitlement_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # monthly / yearly / one_off / prepaid / postpaid

    # ---- 配额 ----
    allocated_tokens: Mapped[int] = mapped_column(BigInt, default=0, nullable=False)
    used_tokens: Mapped[int] = mapped_column(BigInt, default=0, nullable=False)
    overage_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ---- 凭据（只存掩码 + 端点，绝不存明文 Key） ----
    api_key_masked: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # 形如 "sk-xxxx...abc123"
    llm_endpoint: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ---- 备注 ----
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ---- 审计 ----
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TokenEntitlement id={self.id} type={self.entitlement_type}>"


__all__ = ["TokenEntitlement"]
