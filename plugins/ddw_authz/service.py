"""DDW 权限审计插件核心业务逻辑。

内存存储，所有敏感操作自动写入审计日志。
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from .models import (
    AuditLog,
    AuditResult,
    Department,
    Permission,
    Role,
    User,
    UserStatus,
)

logger = logging.getLogger(__name__)


class AuthService:
    """RBAC 权限管理 + 审计日志服务。"""

    def __init__(self) -> None:
        self._users: dict[str, User] = {}
        self._departments: dict[str, Department] = {}
        self._roles: dict[str, Role] = {}
        self._audit_logs: list[AuditLog] = []

    # ---- 审计 ----

    def _record_audit(
        self,
        user_id: str,
        operation: str,
        resource: str,
        result: AuditResult = AuditResult.SUCCESS,
        ip: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> AuditLog:
        log = AuditLog(
            id=uuid.uuid4().hex[:12],
            user_id=user_id,
            operation=operation,
            resource=resource,
            timestamp=datetime.utcnow(),
            ip=ip,
            result=result,
            detail=detail,
        )
        self._audit_logs.append(log)
        logger.info("audit: %s %s/%s -> %s", user_id, operation, resource, result.value)
        return log

    # ========== 用户 CRUD ==========

    def create_user(
        self,
        id: str,
        name: str,
        department_id: Optional[str] = None,
        roles: Optional[list[str]] = None,
        ip: Optional[str] = None,
    ) -> User:
        if id in self._users:
            self._record_audit(id, "create_user", f"user:{id}", AuditResult.ERROR, ip, "用户已存在")
            raise ValueError(f"用户 {id} 已存在")
        user = User(id=id, name=name, department_id=department_id, roles=roles or [])
        self._users[id] = user
        self._record_audit(id, "create_user", f"user:{id}", ip=ip)
        return user

    def get_user(self, user_id: str) -> Optional[User]:
        return self._users.get(user_id)

    def list_users(self) -> list[User]:
        return list(self._users.values())

    def update_user(
        self,
        user_id: str,
        name: Optional[str] = None,
        department_id: Optional[str] = None,
        roles: Optional[list[str]] = None,
        status: Optional[UserStatus] = None,
        operator_id: str = "system",
        ip: Optional[str] = None,
    ) -> Optional[User]:
        user = self._users.get(user_id)
        if not user:
            return None
        if name is not None:
            user.name = name
        if department_id is not None:
            user.department_id = department_id
        if roles is not None:
            user.roles = roles
        if status is not None:
            user.status = status
        self._users[user_id] = user
        self._record_audit(operator_id, "update_user", f"user:{user_id}", ip=ip)
        return user

    def delete_user(
        self, user_id: str, operator_id: str = "system", ip: Optional[str] = None
    ) -> bool:
        if user_id not in self._users:
            return False
        del self._users[user_id]
        self._record_audit(operator_id, "delete_user", f"user:{user_id}", ip=ip)
        return True

    # ========== 部门管理 ==========

    def create_department(
        self,
        id: str,
        name: str,
        parent_id: Optional[str] = None,
        manager_id: Optional[str] = None,
        operator_id: str = "system",
        ip: Optional[str] = None,
    ) -> Department:
        if id in self._departments:
            raise ValueError(f"部门 {id} 已存在")
        if parent_id and parent_id not in self._departments:
            raise ValueError(f"上级部门 {parent_id} 不存在")
        dept = Department(id=id, name=name, parent_id=parent_id, manager_id=manager_id)
        self._departments[id] = dept
        self._record_audit(operator_id, "create_department", f"department:{id}", ip=ip)
        return dept

    def get_department(self, dept_id: str) -> Optional[Department]:
        return self._departments.get(dept_id)

    def list_departments(self) -> list[Department]:
        return list(self._departments.values())

    def get_department_children(self, dept_id: str) -> list[Department]:
        """获取某部门的直接下级部门。"""
        return [d for d in self._departments.values() if d.parent_id == dept_id]

    def get_department_tree(self, root_id: Optional[str] = None) -> list[dict]:
        """递归构建部门树。root_id=None 时返回所有顶层节点。"""
        children = [
            d for d in self._departments.values()
            if d.parent_id == root_id
        ]
        tree = []
        for dept in children:
            node = dept.model_dump()
            node["children"] = self.get_department_tree(dept.id)
            tree.append(node)
        return tree

    # ========== 角色管理 ==========

    def create_role(
        self,
        id: str,
        name: str,
        permissions: Optional[list[Permission]] = None,
        operator_id: str = "system",
        ip: Optional[str] = None,
    ) -> Role:
        if id in self._roles:
            raise ValueError(f"角色 {id} 已存在")
        role = Role(id=id, name=name, permissions=permissions or [])
        self._roles[id] = role
        self._record_audit(operator_id, "create_role", f"role:{id}", ip=ip)
        return role

    def get_role(self, role_id: str) -> Optional[Role]:
        return self._roles.get(role_id)

    def list_roles(self) -> list[Role]:
        return list(self._roles.values())

    def assign_role_to_user(
        self,
        user_id: str,
        role_id: str,
        operator_id: str = "system",
        ip: Optional[str] = None,
    ) -> bool:
        user = self._users.get(user_id)
        if not user:
            return False
        if role_id not in self._roles:
            return False
        if role_id not in user.roles:
            user.roles.append(role_id)
            self._users[user_id] = user
        self._record_audit(operator_id, "assign_role", f"user:{user_id}->role:{role_id}", ip=ip)
        return True

    # ========== 权限校验 ==========

    def has_permission(self, user_id: str, resource: str, action: str) -> bool:
        """检查用户是否拥有指定资源的指定操作权限。

        遍历用户所有角色的权限列表进行匹配。
        """
        user = self._users.get(user_id)
        if not user or user.status != UserStatus.ACTIVE:
            return False
        for role_id in user.roles:
            role = self._roles.get(role_id)
            if not role:
                continue
            for perm in role.permissions:
                if perm.resource == resource and perm.action == action:
                    return True
        return False

    def check_permission(
        self,
        user_id: str,
        resource: str,
        action: str,
        ip: Optional[str] = None,
    ) -> bool:
        """校验权限并自动记录审计日志。"""
        allowed = self.has_permission(user_id, resource, action)
        result = AuditResult.SUCCESS if allowed else AuditResult.DENY
        self._record_audit(
            user_id,
            "check_permission",
            f"{resource}:{action}",
            result=result,
            ip=ip,
        )
        return allowed

    # ========== 审计日志查询 ==========

    def get_audit_logs(
        self,
        user_id: Optional[str] = None,
        operation: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        logs = self._audit_logs
        if user_id:
            logs = [l for l in logs if l.user_id == user_id]
        if operation:
            logs = [l for l in logs if l.operation == operation]
        return logs[-limit:]


__all__ = ["AuthService"]
