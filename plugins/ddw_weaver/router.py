"""泛微E9组织架构集成 API 路由"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel

from plugins.ddw_weaver.models import PortalConfig
from plugins.ddw_weaver.service import WeaverService


# ---- Request schemas ----

class ApiImportReq(BaseModel):
    base_url: str
    app_id: str = ""
    app_secret: str = ""


class DeptMappingReq(BaseModel):
    dept_id: str
    ddw_org_id: str


class PortalConfigReq(BaseModel):
    portal_id: str
    embed_url: str
    css_inject: str = ""
    js_inject: str = ""
    auth_method: str = "sso"


# ---- Module-level service instance ----
_service = WeaverService()


def get_service() -> WeaverService:
    return _service


def build_router(plugin) -> APIRouter:
    r = APIRouter(prefix=plugin.router_prefix, tags=[plugin.name])
    svc = get_service()

    # POST /weaver/import/csv - CSV上传导入
    @r.post("/import/csv")
    async def import_csv(
        file: UploadFile = File(...),
        data_type: str = Form("departments"),
    ) -> Dict[str, Any]:
        content = (await file.read()).decode("utf-8")
        if data_type == "users":
            task = svc.import_users_csv(content)
        else:
            task = svc.import_departments_csv(content)
        return task.model_dump()

    # POST /weaver/import/api - API导入占位
    @r.post("/import/api")
    async def import_api(req: ApiImportReq) -> Dict[str, Any]:
        task = svc.import_from_api(
            base_url=req.base_url,
            app_id=req.app_id,
            app_secret=req.app_secret,
        )
        return task.model_dump()

    # GET /weaver/import/tasks - 导入任务列表
    @r.get("/import/tasks")
    async def list_tasks() -> List[Dict[str, Any]]:
        return [t.model_dump() for t in svc.get_tasks()]

    # GET /weaver/departments - E9部门列表
    @r.get("/departments")
    async def list_departments() -> List[Dict[str, Any]]:
        return [d.model_dump() for d in svc.get_departments()]

    # POST /weaver/departments/mapping - 部门映射
    @r.post("/departments/mapping")
    async def map_department(req: DeptMappingReq) -> Dict[str, Any]:
        ok = svc.map_department(req.dept_id, req.ddw_org_id)
        return {"success": ok}

    # GET /weaver/users - E9用户列表
    @r.get("/users")
    async def list_users() -> List[Dict[str, Any]]:
        return [u.model_dump() for u in svc.get_users()]

    # POST /weaver/portal/config - 门户配置
    @r.post("/portal/config")
    async def save_portal_config(req: PortalConfigReq) -> Dict[str, Any]:
        config = PortalConfig(
            portal_id=req.portal_id,
            embed_url=req.embed_url,
            css_inject=req.css_inject,
            js_inject=req.js_inject,
            auth_method=req.auth_method,
        )
        saved = svc.save_portal_config(config)
        return saved.model_dump()

    # GET /weaver/portal/config - 门户配置列表
    @r.get("/portal/config")
    async def list_portal_configs() -> List[Dict[str, Any]]:
        return [c.model_dump() for c in svc.list_portal_configs()]

    return r
