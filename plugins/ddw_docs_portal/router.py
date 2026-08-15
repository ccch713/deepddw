"""产品文档栏目 API 路由。

端点（13 个）：
  健康：GET    /health
  目录：GET    /categories  POST /categories  PATCH /categories/{id}
  文档：GET    /docs  GET /docs/{id}  POST /docs  PATCH /docs/{id}
        POST /docs/{id}/publish  POST /docs/{id}/archive
  检索：GET    /search?q=&top_k=
  离线：POST   /export  POST /import

权限：读=登录（未登录 401，白皮书红线）；写=superadmin/租户管理员；
      tenant 文档仅本租户（跨租户 403）；draft 仅作者+管理员。
双轨制：docs_* 表查询一律 bypass_tenant_filter + 显式租户过滤（服务层实现）。
"""
from __future__ import annotations

import logging
from typing import Optional

from core.auth.jwt import current_user
from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter
from fastapi import APIRouter, Depends, Query, Request, Response

from . import PLUGIN_NAME, VERSION
from .models import (
    CategoryCreateReq,
    CategoryUpdateReq,
    DocCreateReq,
    DocUpdateReq,
    ImportPackageReq,
)
from .services import DocsPortalService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造文档栏目路由。"""
    router = APIRouter(
        prefix=f"/api/v1/plugins/{PLUGIN_NAME}",
        tags=["ddw-docs-portal"],
    )

    @router.get("/health")
    async def health() -> dict:
        return {"plugin": PLUGIN_NAME, "version": VERSION, "status": "ok"}

    # ─── 目录 ──────────────────────────────────────────────────

    @router.get("/categories", response_model=list)
    async def list_categories(user: dict = Depends(current_user)) -> list:
        """目录树（平台级 0 + 本租户，登录可见）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = DocsPortalService(db)
            return await svc.list_categories_tree(user)

    @router.post("/categories", status_code=201)
    async def create_category(
        data: CategoryCreateReq, user: dict = Depends(current_user)
    ) -> dict:
        """建分类（superadmin 或租户管理员）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = DocsPortalService(db)
            return await svc.create_category(data, user)

    @router.patch("/categories/{category_id}")
    async def update_category(
        category_id: int,
        data: CategoryUpdateReq,
        user: dict = Depends(current_user),
    ) -> dict:
        """改分类（同名权限）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = DocsPortalService(db)
            return await svc.update_category(category_id, data, user)

    # ─── 文档 ──────────────────────────────────────────────────

    @router.get("/docs", response_model=dict)
    async def list_docs(
        category_id: Optional[int] = Query(None, description="目录过滤"),
        doc_type: Optional[str] = Query(None, description="类型过滤"),
        visibility: Optional[str] = Query(None, description="可见性过滤"),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        user: dict = Depends(current_user),
    ) -> dict:
        """文档列表（目录+可见性过滤，只返回当前用户可见文档）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = DocsPortalService(db)
            return await svc.list_docs(
                user, category_id=category_id, doc_type=doc_type,
                visibility=visibility, page=page, page_size=page_size,
            )

    @router.get("/docs/{doc_id}")
    async def get_doc(doc_id: int, user: dict = Depends(current_user)) -> dict:
        """文档详情（元数据 + 从 doc_assistant 重建的正文）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = DocsPortalService(db)
            return await svc.get_doc(doc_id, user)

    @router.post("/docs", status_code=201)
    async def create_doc(
        data: DocCreateReq, user: dict = Depends(current_user)
    ) -> dict:
        """新建文档（内容 → doc_assistant ingest → source_ref）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = DocsPortalService(db)
            return await svc.create_doc(data, user)

    @router.patch("/docs/{doc_id}")
    async def update_doc(
        doc_id: int, data: DocUpdateReq, user: dict = Depends(current_user)
    ) -> dict:
        """更新文档（重新 ingest → version 递增 → DocVersion 记录）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = DocsPortalService(db)
            return await svc.update_doc(doc_id, data, user)

    @router.post("/docs/{doc_id}/publish")
    async def publish_doc(
        doc_id: int, user: dict = Depends(current_user)
    ) -> dict:
        """发布（draft→published；写 enterprise 记忆，按 doc_id upsert）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = DocsPortalService(db)
            return await svc.publish_doc(doc_id, user)

    @router.post("/docs/{doc_id}/archive")
    async def archive_doc(
        doc_id: int, user: dict = Depends(current_user)
    ) -> dict:
        """归档（published→archived；记忆标记 archived 不删除）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = DocsPortalService(db)
            return await svc.archive_doc(doc_id, user)

    # ─── 检索（LLM/前端/客服统一入口，决策 3） ──────────────────

    @router.get("/search")
    async def search_docs(
        q: str = Query(..., min_length=1, max_length=400, description="检索词"),
        top_k: int = Query(5, ge=1, le=20),
        user: dict = Depends(current_user),
    ) -> dict:
        """混合检索（委托 doc_assistant；只搜 published + 当前用户可见）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = DocsPortalService(db)
            return await svc.search_docs(q, top_k, user)

    # ─── 离线部署包（决策 4，M5） ───────────────────────────────

    @router.post("/export")
    async def export_package(user: dict = Depends(current_user)) -> dict:
        """导出发布快照（manifest + content_hash，管理员）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = DocsPortalService(db)
            return await svc.export_package(user)

    @router.post("/import")
    async def import_package(
        request: Request, response: Response, data: ImportPackageReq,
        user: dict = Depends(current_user)
    ) -> dict:
        """导入离线更新包（按 content_hash 去重幂等，管理员）。"""
        # P3 数据同步授权校验 + P4 捎带响应头：旧码超 7 天倒计时 → 拒绝同步
        from core.utils.license_broker import state_response_headers
        from core.utils.license_state import check_sync_allowed

        sync_allowed, sync_reason = check_sync_allowed(
            request.headers.get("X-DDW-License-Key")
        )
        _state_headers = state_response_headers()
        if not sync_allowed:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=403,
                content={"detail": sync_reason},
                headers=_state_headers,
            )
        response.headers.update(_state_headers)

        async with session_scope() as db, bypass_tenant_filter():
            svc = DocsPortalService(db)
            return await svc.import_package(data, user)

    return router


__all__ = ["build_router"]
