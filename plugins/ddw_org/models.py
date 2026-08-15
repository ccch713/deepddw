"""DDW AI 组织插件 ORM 模型。

使用 core.database.session.Base（平台统一 DeclarativeBase），
以支持跨表 Foreign Key（tenants.id / users.id）。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.session import Base


class Department(Base):
    """部门。"""

    __tablename__ = "org_departments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "preset_id", name="uq_dept_tenant_preset"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    preset_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    manager_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    agents: Mapped[List["DigitalAgent"]] = relationship(
        "DigitalAgent", back_populates="department", cascade="all, delete-orphan"
    )
    employees: Mapped[List["OrgEmployee"]] = relationship(
        "OrgEmployee", back_populates="department"
    )


class DigitalAgent(Base):
    """数字员工。"""

    __tablename__ = "org_digital_agents"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    department_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("org_departments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(100), default="")
    avatar_color: Mapped[str] = mapped_column(String(20), default="#1890FF")
    status: Mapped[str] = mapped_column(String(20), default="online")
    description: Mapped[str] = mapped_column(Text, default="")
    preset_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    default_skills: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    job_objective: Mapped[str] = mapped_column(Text, default="")
    report_to: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decision_scope: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    work_boundary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    department: Mapped["Department"] = relationship("Department", back_populates="agents")
    agent_skills: Mapped[List["AgentSkill"]] = relationship(
        "AgentSkill", back_populates="agent", cascade="all, delete-orphan"
    )


class OrgEmployee(Base):
    """员工。"""

    __tablename__ = "org_employees"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    department_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("org_departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    title: Mapped[str] = mapped_column(String(100), default="")
    wecom_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    department: Mapped[Optional["Department"]] = relationship(
        "Department", back_populates="employees"
    )


class AgentSkill(Base):
    """数字员工-Skill 关联。"""

    __tablename__ = "org_agent_skills"
    __table_args__ = (
        UniqueConstraint("agent_id", "skill_id", name="uq_agent_skill"),
        {"extend_existing": True},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("org_digital_agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_id: Mapped[int] = mapped_column(Integer, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    proficiency: Mapped[str] = mapped_column(String(20), default="junior")
    trigger_conditions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    sla_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    assigned_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    agent: Mapped["DigitalAgent"] = relationship("DigitalAgent", back_populates="agent_skills")


class OrgSkillPool(Base):
    """Skill 池（占位，TASK_SPEC_SKILL_POOL 就绪后替换）。"""

    __tablename__ = "org_skill_pool"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(50), default="general")


class DigitalAgentTemplate(Base):
    """数字员工模板。"""

    __tablename__ = "digital_agent_templates"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_name: Mapped[str] = mapped_column(String(200), nullable=False)
    template_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="employee_created"
    )
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    department_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("org_departments.id"), nullable=False, index=True
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    job_objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    decision_scope: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, default=list
    )
    work_boundary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    input_spec: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    output_spec: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    validation_results: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    approval_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


__all__ = [
    "AgentSkill",
    "Department",
    "DigitalAgent",
    "DigitalAgentTemplate",
    "OrgEmployee",
    "OrgSkillPool",
]
