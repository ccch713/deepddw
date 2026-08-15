"""泛微E9组织架构 Pydantic 模型"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class WeaverDepartment(BaseModel):
    """E9部门"""
    dept_id: str = Field(..., description="E9部门ID")
    name: str = Field(..., description="部门名称")
    code: str = Field("", description="部门编码")
    parent_id: Optional[str] = Field(None, description="上级部门ID")
    ddw_org_id: Optional[str] = Field(None, description="DDW映射组织ID")


class WeaverUser(BaseModel):
    """E9用户"""
    user_id: str = Field(..., description="E9用户ID")
    name: str = Field(..., description="姓名")
    employee_no: str = Field("", description="工号")
    dept_id: str = Field("", description="所属部门ID")
    position: str = Field("", description="职位")
    status: str = Field("active", description="状态: active/inactive")


class ImportSource(str, Enum):
    CSV = "csv"
    API = "api"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ImportTask(BaseModel):
    """导入任务"""
    task_id: str = Field(..., description="任务ID")
    source: ImportSource = Field(..., description="来源: csv/api")
    status: TaskStatus = Field(TaskStatus.PENDING, description="任务状态")
    imported_count: int = Field(0, description="导入数量")
    error_count: int = Field(0, description="错误数")
    errors: list[str] = Field(default_factory=list, description="错误详情")
    created_at: str = Field("", description="创建时间")


class AuthMethod(str, Enum):
    SSO = "sso"
    TOKEN = "token"
    NONE = "none"


class PortalConfig(BaseModel):
    """门户嵌入配置"""
    portal_id: str = Field(..., description="门户ID")
    embed_url: str = Field(..., description="嵌入URL")
    css_inject: str = Field("", description="CSS注入内容")
    js_inject: str = Field("", description="JS注入内容")
    auth_method: AuthMethod = Field(AuthMethod.SSO, description="认证方式")
