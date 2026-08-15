"""DDW 报表插件 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database.session import Base

# 兼容 SQLite
BigInt = Integer()


class ReportCache(Base):
    """报表缓存表（避免每次重新聚合）。"""

    __tablename__ = "ddw_report_cache"
    __table_args__ = {"extend_existing": True}
    __tenant_aware__ = True  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    report_key: Mapped[str] = mapped_column(String(200), nullable=False, index=True)  # e.g. "user:123:monthly:2026-07"
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)  # user_daily / user_weekly / user_monthly / class_overview
    user_id: Mapped[Optional[int]] = mapped_column(BigInt, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


__all__ = ["ReportCache"]
