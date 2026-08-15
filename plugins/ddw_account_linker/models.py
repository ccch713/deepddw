"""DDW 账号打通插件 ORM 模型。

继承 DDW 平台核心：
- core.database.session.Base: DeclarativeBase 根
- core.database.models.TenantMixin: 自动注入 tenant_id + 标记租户感知
- core.database.models.TimestampMixin: 自动注入 created_at / updated_at
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import Base, TenantMixin, TimestampMixin

# BigInteger 在 SQLite 不支持 -> 退化到 Integer
BigInt = BigInteger().with_variant(Integer(), "sqlite")


class AccountLink(Base, TenantMixin, TimestampMixin):
    """账号打通记录（DDW 账号与外部系统账号的绑定关系）。"""

    __tablename__ = "crm_account_links"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)

    # ---- 关联 ----
    company_id: Mapped[Optional[int]] = mapped_column(
        BigInt,
        ForeignKey("crm_companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ---- 外部系统 ----
    link_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # wechat_work / dingtalk / feishu / oauth / sso / custom
    external_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    external_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ---- 扩展属性（按 link_type 不同可放 unionid / openid / tenant_key 等） ----
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # ---- 状态 ----
    status: Mapped[str] = mapped_column(
        String(20), default="active", nullable=False, index=True
    )  # active / expired / revoked

    # ---- 审计 ----
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AccountLink id={self.id} type={self.link_type} external_id={self.external_id!r}>"


__all__ = ["AccountLink"]
