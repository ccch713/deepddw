"""DDW 权限审计插件 Pydantic 数据模型。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    LOCKED = "locked"


class AuditResult(str, Enum):
    SUCCESS = "success"
    DENY = "deny"
    ERROR = "error"


class Permission(BaseModel):
    resource: str = Field(..., description="资源标识，如 order、user、report")
    action: str = Field(..., description="操作类型，如 read、write、delete")
    role_id: Optional[str] = Field(None, description="绑定的角色 ID")


class Role(BaseModel):
    id: str = Field(..., description="角色 ID")
    name: str = Field(..., description="角色名称")
    permissions: list[Permission] = Field(default_factory=list, description="权限列表")


class Department(BaseModel):
    id: str = Field(..., description="部门 ID")
    name: str = Field(..., description="部门名称")
    parent_id: Optional[str] = Field(None, description="上级部门 ID，顶层为 None")
    manager_id: Optional[str] = Field(None, description="负责人用户 ID")


class User(BaseModel):
    id: str = Field(..., description="用户 ID")
    name: str = Field(..., description="用户姓名")
    department_id: Optional[str] = Field(None, description="所属部门 ID")
    roles: list[str] = Field(default_factory=list, description="角色 ID 列表")
    status: UserStatus = Field(UserStatus.ACTIVE, description="用户状态")


class AuditLog(BaseModel):
    id: str = Field(..., description="操作 ID")
    user_id: str = Field(..., description="操作用户 ID")
    operation: str = Field(..., description="操作类型，如 create_user、delete_role")
    resource: str = Field(..., description="操作资源")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="操作时间")
    ip: Optional[str] = Field(None, description="操作 IP 地址")
    result: AuditResult = Field(AuditResult.SUCCESS, description="操作结果")
    detail: Optional[str] = Field(None, description="补充说明")


__all__ = [
    "AuditLog",
    "AuditResult",
    "Department",
    "Permission",
    "Role",
    "User",
    "UserStatus",
]
