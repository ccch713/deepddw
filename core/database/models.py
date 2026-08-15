"""deepDDW 核心 ORM 模型（开源裁剪版）。

只保留白名单组件所需的最小模型集合：
- :class:`KnowledgeBase` / :class:`KnowledgeBasePermission` — 个人级知识库（SQLite + LanceDB）
- :class:`TimestampMixin` — 时间戳混入

账号体系（User/Tenant/TokenQuota/ApiKey）、计费授权（LicenseKey/OnPremiseCustomer）、
培训（TrainingSession/TrainingAssessment）、渠道（ChannelPartner）、市场/论坛、
IM 审计等商业模型一律移除（deepDDW 0.1 无账号、无租户、无授权体系）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database.session import Base

# BigInteger 在 SQLite 不支持 AUTOINCREMENT → 退化到 Integer（保留 PG 上的 BigInt）
BigInt = Integer


class TimestampMixin:
    """时间戳混入。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class KnowledgeBase(Base, TimestampMixin):
    """知识库（个人级，deepDDW 白名单组件）。"""

    __tablename__ = "kb_bases"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)


class KnowledgeBasePermission(Base):
    """知识库权限矩阵（单用户版：保留表结构，tenant_id 恒为 0）。"""

    __tablename__ = "kb_base_permissions"
    __table_args__ = (
        UniqueConstraint("base_id", "tenant_id", name="uq_kb_perm_base_tenant"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    base_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kb_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True, default=0)
    permissions: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


__all__ = ["BigInt", "TimestampMixin", "KnowledgeBase", "KnowledgeBasePermission"]
