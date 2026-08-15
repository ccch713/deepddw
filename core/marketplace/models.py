"""SQLAlchemy ORM 模型 — 插件市场相关表。

包含插件上架信息、安装记录、评价三张核心表。
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database.factory import Base
from core.database.types import JSONEncodedText, String191, UTCDateTime

# ---------------------------------------------------------------------------
# 插件上架信息表
# ---------------------------------------------------------------------------


class PluginListing(Base):
    """插件上架信息 — 市场元数据。

    与 InstalledPlugin 不同，这张表记录「市场上有哪些插件」，
    而 InstalledPlugin 记录「本实例装了哪些插件」。
    """

    __tablename__ = "market_plugin_listings"
    __table_args__ = (
        UniqueConstraint("name", name="uq_plugin_listing_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String191, nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author: Mapped[str] = mapped_column(String(128), default="Unknown", nullable=False)
    license: Mapped[str] = mapped_column(String(32), default="MIT", nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="other", nullable=False)
    rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    downloads: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tags: Mapped[Optional[dict]] = mapped_column(JSONEncodedText, nullable=True)
    icon_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    homepage: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    engine: Mapped[str] = mapped_column(String(32), default=">=0.1.0", nullable=False)
    permissions: Mapped[Optional[dict]] = mapped_column(JSONEncodedText, nullable=True)
    dependencies: Mapped[Optional[dict]] = mapped_column(JSONEncodedText, nullable=True)
    config_schema: Mapped[Optional[dict]] = mapped_column(JSONEncodedText, nullable=True)
    manifest_raw: Mapped[Optional[dict]] = mapped_column(JSONEncodedText, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# 插件安装记录表
# ---------------------------------------------------------------------------


class PluginInstall(Base):
    """插件安装记录 — 跟踪本实例的安装状态。"""

    __tablename__ = "market_plugin_installs"
    __table_args__ = (
        UniqueConstraint("plugin_name", name="uq_plugin_install_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    plugin_name: Mapped[str] = mapped_column(String191, nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    isolation: Mapped[str] = mapped_column(String(16), default="inline", nullable=False)
    config: Mapped[Optional[dict]] = mapped_column(JSONEncodedText, nullable=True)

    installed_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# 插件评价表
# ---------------------------------------------------------------------------


class PluginReview(Base):
    """插件评价 — 用户对插件的评分和评论。"""

    __tablename__ = "market_plugin_reviews"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    plugin_name: Mapped[str] = mapped_column(String191, nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        UTCDateTime, server_default=func.now(), nullable=False
    )
