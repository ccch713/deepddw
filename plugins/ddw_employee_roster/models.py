"""员工花名册 ORM 模型"""
from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import Base, TenantMixin, TimestampMixin


class Employee(Base, TenantMixin, TimestampMixin):
    __tablename__ = "employees"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_no: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[str] = mapped_column(String(100), default="")
    position: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    email: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="active")

class EmployeeTrainingRecord(Base, TenantMixin, TimestampMixin):
    __tablename__ = "employee_training_records"
    __table_args__ = {"extend_existing": True}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    session_uuid: Mapped[str] = mapped_column(String(32), default="")
    subject: Mapped[str] = mapped_column(String(40), default="")
    course_id: Mapped[str] = mapped_column(String(80), default="")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[int] = mapped_column(Integer, default=0)
    grade: Mapped[str] = mapped_column(String(10), default="")
    completed_at: Mapped[str] = mapped_column(String(30), default="")
