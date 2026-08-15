"""DDW AI 组织插件 Pydantic schemas。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── 部门 ────────────────────────────────────────────────────────────────


class DepartmentCreateReq(BaseModel):
    """新建部门请求。"""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field("", max_length=2000)
    sort_order: Optional[int] = Field(0)
    preset_id: Optional[str] = Field(None, max_length=50)


class DepartmentUpdateReq(BaseModel):
    """修改部门请求。"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    sort_order: Optional[int] = None
    manager_user_id: Optional[int] = None


class DepartmentResp(BaseModel):
    """部门响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    name: str
    description: str = ""
    sort_order: int = 0
    preset_id: Optional[str] = None
    manager_user_id: Optional[int] = None
    digital_agent_count: Optional[int] = None
    employee_count: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DepartmentDetailResp(BaseModel):
    """部门详情响应（含数字员工 + 员工列表）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    name: str
    description: str = ""
    sort_order: int = 0
    preset_id: Optional[str] = None
    manager_user_id: Optional[int] = None
    agents: List[Dict[str, Any]] = []
    employees: List[Dict[str, Any]] = []
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── 数字员工 ────────────────────────────────────────────────────────────


class AgentUpdateReq(BaseModel):
    """修改数字员工请求。"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    role: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    avatar_color: Optional[str] = Field(None, max_length=20)
    status: Optional[str] = Field(None, max_length=20)
    job_objective: Optional[str] = None
    report_to: Optional[int] = None
    decision_scope: Optional[List[str]] = None
    work_boundary: Optional[str] = None


class AgentResp(BaseModel):
    """数字员工响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    department_id: int
    name: str
    role: str = ""
    avatar_color: str = "#1890FF"
    status: str = "online"
    description: str = ""
    preset_id: Optional[str] = None
    default_skills: List[str] = []
    job_objective: str = ""
    report_to: Optional[int] = None
    decision_scope: List[str] = []
    work_boundary: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AgentDetailResp(AgentResp):
    """数字员工详情响应（含已分配 skill）。"""

    skills: List[Dict[str, Any]] = []


# ── 员工 ────────────────────────────────────────────────────────────────


class EmployeeCreateReq(BaseModel):
    """新增员工请求。"""

    name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    title: Optional[str] = Field("", max_length=100)
    department_id: Optional[int] = None
    wecom_id: Optional[str] = Field(None, max_length=100)


class EmployeeUpdateReq(BaseModel):
    """修改员工请求。"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    title: Optional[str] = Field(None, max_length=100)
    department_id: Optional[int] = None
    wecom_id: Optional[str] = Field(None, max_length=100)
    status: Optional[str] = Field(None, max_length=20)


class EmployeeResp(BaseModel):
    """员工响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    department_id: Optional[int] = None
    user_id: Optional[int] = None
    name: str
    phone: Optional[str] = None
    title: str = ""
    wecom_id: Optional[str] = None
    source: str = "manual"
    status: str = "active"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── Skill ───────────────────────────────────────────────────────────────


class SkillAssignReq(BaseModel):
    """分配 skill 请求。"""

    skill_id: int


class AgentSkillUpdateReq(BaseModel):
    """更新 agent-skill 关联请求。"""

    enabled: Optional[bool] = None
    proficiency: Optional[str] = Field(None, max_length=20)
    trigger_conditions: Optional[List[Dict[str, Any]]] = None
    sla_seconds: Optional[int] = None

    @field_validator("proficiency")
    @classmethod
    def validate_proficiency(cls, v: str) -> str:
        if v not in ("junior", "senior", "expert"):
            raise ValueError(f"proficiency 必须是 junior/senior/expert，收到: {v}")
        return v

    @field_validator("trigger_conditions")
    @classmethod
    def validate_triggers(cls, v: list) -> list:
        for item in v:
            if not isinstance(item, dict) or "event" not in item:
                raise ValueError("每个 trigger_condition 必须包含 'event' 字段")
        return v

    @field_validator("sla_seconds")
    @classmethod
    def validate_sla(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("sla_seconds 不能为负数")
        return v


class DigitalAgentJobCard(BaseModel):
    """数字员工岗位卡响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: str
    department_name: str
    job_objective: str
    report_to_name: Optional[str] = None
    decision_scope: List[str] = []
    work_boundary: str
    skills: List[Dict[str, Any]] = []
    status: str


class SkillPoolResp(BaseModel):
    """Skill 池项响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    skill_key: str
    name: str
    description: str = ""
    category: str = "general"


# ── 数字员工模板 ────────────────────────────────────────────────────────


class TemplateCreateReq(BaseModel):
    """创建模板请求。"""

    template_name: str = Field(..., min_length=1, max_length=200)
    template_type: Optional[str] = Field("employee_created", max_length=20)
    department_id: int
    agent_name: str = Field(..., min_length=1, max_length=100)
    job_objective: Optional[str] = Field("", max_length=5000)
    role: str = Field(..., min_length=1, max_length=100)
    decision_scope: Optional[List[str]] = Field(default_factory=list)
    work_boundary: Optional[str] = Field("", max_length=5000)
    skills: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    input_spec: Optional[Dict[str, Any]] = None
    output_spec: Optional[Dict[str, Any]] = None


class TemplateResp(BaseModel):
    """模板响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    template_name: str
    template_type: str = "employee_created"
    created_by: int
    department_id: int
    agent_name: str
    job_objective: str = ""
    role: str
    decision_scope: List[str] = []
    work_boundary: str = ""
    skills: List[Dict[str, Any]] = []
    input_spec: Optional[Dict[str, Any]] = None
    output_spec: Optional[Dict[str, Any]] = None
    status: str = "draft"
    validation_results: Optional[Dict[str, Any]] = None
    approval_status: str = "pending"
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ── 通用 ────────────────────────────────────────────────────────────────


class SeedResp(BaseModel):
    """种子数据响应。"""

    departments: int = 0
    agents: int = 0
    skills: int = 0
    skipped: bool = False


__all__ = [
    "AgentDetailResp",
    "AgentResp",
    "AgentSkillUpdateReq",
    "AgentUpdateReq",
    "DepartmentCreateReq",
    "DepartmentDetailResp",
    "DepartmentResp",
    "DepartmentUpdateReq",
    "DigitalAgentJobCard",
    "EmployeeCreateReq",
    "EmployeeResp",
    "EmployeeUpdateReq",
    "SeedResp",
    "SkillAssignReq",
    "SkillPoolResp",
    "TemplateCreateReq",
    "TemplateResp",
]
