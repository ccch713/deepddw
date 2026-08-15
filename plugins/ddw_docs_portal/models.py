"""产品文档栏目插件 ORM + Pydantic 模型。

三张表（平台主库 data/ddw_main.db，表名前缀 docs_）：
- docs_category: 文档目录节点（树形）
- docs_item: 文档元数据（内容实际存 ddw_doc_assistant，source_ref 引用其 doc_id）
- docs_version: 版本历史

租户模型：双轨制（PRD 决策 1）—— tenant_id=0 平台级（白皮书/手册，全租户登录可见）；
tenant_id>0 租户级（客户规章制度，仅本租户）。不做跨租户共享表。
"""
from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Optional

from core.database.models import Base, TenantMixin, TimestampMixin
from pydantic import BaseModel, Field
from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

# BigInteger 在 SQLite 不支持 -> 退化到 Integer
BigInt = BigInteger().with_variant(Integer(), "sqlite")

# 枚举常量（权限判断统一引用）
DOC_TYPES = ("whitepaper", "manual", "solution", "regulation", "notice")
VISIBILITY = ("public", "tenant", "draft")
STATUS = ("draft", "published", "archived")


class DocCategory(Base, TenantMixin, TimestampMixin):
    """文档目录节点（树形，parent_id 指向上级分类）。"""

    __tablename__ = "docs_category"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_docs_category_tenant_slug"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    parent_id: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class DocItem(Base, TenantMixin, TimestampMixin):
    """文档元数据。内容正文只存 ddw_doc_assistant（source_ref），portal 不双写内容。"""

    __tablename__ = "docs_item"
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_docs_item_tenant_slug"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    category_id: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(
        String(32), default="whitepaper", nullable=False
    )  # whitepaper/manual/solution/regulation/notice
    visibility: Mapped[str] = mapped_column(
        String(16), default="tenant", nullable=False
    )  # public（全租户）/tenant（本租户）/draft（仅作者+管理员）
    status: Mapped[str] = mapped_column(
        String(16), default="draft", nullable=False
    )  # draft/published/archived
    version: Mapped[str] = mapped_column(String(16), default="v1.0", nullable=False)
    source_ref: Mapped[str] = mapped_column(
        String(64), default="", nullable=False
    )  # 指向 ddw_doc_assistant 的 doc_id（内容存那边）
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )  # 重建正文 sha256（离线包导入去重幂等，决策 4）
    summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # ≤200 字摘要，publish 时写入 enterprise 记忆
    author_id: Mapped[int] = mapped_column(BigInt, default=0, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class DocVersion(Base, TenantMixin, TimestampMixin):
    """版本历史：每次更新（PATCH）记录旧 source_ref，保证旧版本可查（归档语义）。"""

    __tablename__ = "docs_version"
    __table_args__: ClassVar[dict] = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(BigInt, nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    change_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_ref: Mapped[str] = mapped_column(String(64), default="", nullable=False)


# ─── Pydantic: 请求 ───


class CategoryCreateReq(BaseModel):
    """建分类请求。"""

    name: str = Field(..., min_length=1, max_length=200)
    slug: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9-]+$")
    parent_id: Optional[int] = None
    sort_order: int = Field(0, ge=0)


class CategoryUpdateReq(BaseModel):
    """改分类请求（字段可选）。"""

    name: Optional[str] = Field(None, min_length=1, max_length=200)
    slug: Optional[str] = Field(None, min_length=1, max_length=128, pattern=r"^[a-z0-9-]+$")
    parent_id: Optional[int] = None
    sort_order: Optional[int] = Field(None, ge=0)


class DocCreateReq(BaseModel):
    """新建文档请求。content 为正文（markdown/纯文本），内部写入 doc_assistant。"""

    title: str = Field(..., min_length=1, max_length=500)
    slug: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-z0-9-]+$")
    category_id: Optional[int] = None
    doc_type: str = Field("whitepaper")
    visibility: str = Field("tenant")
    content: str = Field(..., min_length=1, description="文档正文（markdown 或纯文本）")
    summary: Optional[str] = Field(None, max_length=500, description="≤200 字摘要，publish 时进 enterprise 记忆")
    version: Optional[str] = Field(None, description="显式指定版本号（默认 v1.0）")


class DocUpdateReq(BaseModel):
    """更新文档请求（content 与 version 可选）。"""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    slug: Optional[str] = Field(None, min_length=1, max_length=128, pattern=r"^[a-z0-9-]+$")
    category_id: Optional[int] = None
    doc_type: Optional[str] = None
    visibility: Optional[str] = None
    content: Optional[str] = Field(None, min_length=1)
    summary: Optional[str] = Field(None, max_length=500)
    version: Optional[str] = Field(None)


class ImportPackageReq(BaseModel):
    """离线更新包导入请求（决策 4，按 content_hash 去重幂等）。"""

    tenant_id: int = Field(0, description="导入归属租户（0=平台级产品文档包；>0=租户制度包）")
    docs: list[dict] = Field(default_factory=list, description="每项: {doc_id, slug, version, title, content_hash, exported_at, content, visibility}")


__all__ = [
    "DOC_TYPES",
    "STATUS",
    "VISIBILITY",
    "CategoryCreateReq",
    "CategoryUpdateReq",
    "DocCategory",
    "DocCreateReq",
    "DocItem",
    "DocUpdateReq",
    "DocVersion",
    "ImportPackageReq",
]
