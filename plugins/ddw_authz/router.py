"""DDW 权限审计插件 API 路由。"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .models import Permission, UserStatus
from .service import AuthService

logger = logging.getLogger(__name__)

# 全局单例（插件生命周期内）
_service = AuthService()


def get_service() -> AuthService:
    return _service


# ---- Request Schemas ----


class UserCreateReq(BaseModel):
    id: str
    name: str
    department_id: Optional[str] = None
    roles: list[str] = []


class UserUpdateReq(BaseModel):
    name: Optional[str] = None
    department_id: Optional[str] = None
    roles: Optional[list[str]] = None
    status: Optional[UserStatus] = None


class DepartmentCreateReq(BaseModel):
    id: str
    name: str
    parent_id: Optional[str] = None
    manager_id: Optional[str] = None


class RoleCreateReq(BaseModel):
    id: str
    name: str
    permissions: list[Permission] = []


class CheckPermissionReq(BaseModel):
    user_id: str
    resource: str
    action: str


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/plugins/ddw-authz", tags=["ddw-authz"])

    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-authz", "version": "1.0.0", "status": "ok"}

    # ---- 用户 CRUD ----

    @router.post("/users", status_code=201)
    async def create_user(data: UserCreateReq) -> dict:
        svc = get_service()
        try:
            user = svc.create_user(
                id=data.id, name=data.name,
                department_id=data.department_id, roles=data.roles,
            )
            return user.model_dump()
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

    @router.get("/users")
    async def list_users() -> list[dict]:
        svc = get_service()
        return [u.model_dump() for u in svc.list_users()]

    @router.get("/users/{user_id}")
    async def get_user(user_id: str) -> dict:
        svc = get_service()
        user = svc.get_user(user_id)
        if not user:
            raise HTTPException(status_code=404, detail=f"user {user_id} not found")
        return user.model_dump()

    @router.put("/users/{user_id}")
    async def update_user(user_id: str, data: UserUpdateReq) -> dict:
        svc = get_service()
        user = svc.update_user(
            user_id, name=data.name, department_id=data.department_id,
            roles=data.roles, status=data.status,
        )
        if not user:
            raise HTTPException(status_code=404, detail=f"user {user_id} not found")
        return user.model_dump()

    @router.delete("/users/{user_id}")
    async def delete_user(user_id: str) -> dict:
        svc = get_service()
        ok = svc.delete_user(user_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"user {user_id} not found")
        return {"deleted": True, "id": user_id}

    # ---- 部门 ----

    @router.post("/departments", status_code=201)
    async def create_department(data: DepartmentCreateReq) -> dict:
        svc = get_service()
        try:
            dept = svc.create_department(
                id=data.id, name=data.name,
                parent_id=data.parent_id, manager_id=data.manager_id,
            )
            return dept.model_dump()
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

    @router.get("/departments")
    async def list_departments() -> list[dict]:
        svc = get_service()
        return [d.model_dump() for d in svc.list_departments()]

    @router.get("/departments/tree")
    async def department_tree() -> list[dict]:
        svc = get_service()
        return svc.get_department_tree()

    # ---- 角色 ----

    @router.post("/roles", status_code=201)
    async def create_role(data: RoleCreateReq) -> dict:
        svc = get_service()
        try:
            role = svc.create_role(
                id=data.id, name=data.name, permissions=data.permissions,
            )
            return role.model_dump()
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))

    @router.get("/roles")
    async def list_roles() -> list[dict]:
        svc = get_service()
        return [r.model_dump() for r in svc.list_roles()]

    # ---- 权限校验 ----

    @router.post("/check-permission")
    async def check_permission(data: CheckPermissionReq) -> dict:
        svc = get_service()
        allowed = svc.check_permission(data.user_id, data.resource, data.action)
        return {"user_id": data.user_id, "resource": data.resource, "action": data.action, "allowed": allowed}

    # ---- 审计日志 ----

    @router.get("/audit-logs")
    async def get_audit_logs(
        user_id: Optional[str] = Query(None),
        operation: Optional[str] = Query(None),
        limit: int = Query(100, ge=1, le=1000),
    ) -> list[dict]:
        svc = get_service()
        logs = svc.get_audit_logs(user_id=user_id, operation=operation, limit=limit)
        return [l.model_dump() for l in logs]

    return router


__all__ = ["build_router", "get_service"]
