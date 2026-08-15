"""计费 ORM 模型"""
from __future__ import annotations

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import Base, TenantMixin, TimestampMixin


class Subscription(Base, TenantMixin, TimestampMixin):
    __tablename__ = "subscriptions"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    plan_name: Mapped[str] = mapped_column(String(50), default="free")
    status: Mapped[str] = mapped_column(String(20), default="active")
    start_date: Mapped[str] = mapped_column(String(20), default="")
    end_date: Mapped[str] = mapped_column(String(20), default="")
    monthly_limit: Mapped[int] = mapped_column(Integer, default=1000)
    used: Mapped[int] = mapped_column(Integer, default=0)

class UsageLog(Base, TenantMixin, TimestampMixin):
    __tablename__ = "usage_logs"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, default=0)
    event_type: Mapped[str] = mapped_column(String(50), default="")
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
