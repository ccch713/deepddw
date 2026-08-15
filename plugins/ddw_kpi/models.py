"""KPI ORM 模型"""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import Base, TenantMixin, TimestampMixin


class KpiRule(Base, TenantMixin, TimestampMixin):
    __tablename__ = "kpi_rules"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rule_name: Mapped[str] = mapped_column(String(100), nullable=False)
    subject: Mapped[str] = mapped_column(String(40), default="")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    threshold: Mapped[float] = mapped_column(Float, default=60.0)
    formula: Mapped[str] = mapped_column(Text, default="average_score")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

class KpiRecord(Base, TenantMixin, TimestampMixin):
    __tablename__ = "kpi_records"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, index=True)
    rule_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    period: Mapped[str] = mapped_column(String(20), default="")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    details_json: Mapped[str] = mapped_column(Text, default="{}")
