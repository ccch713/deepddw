"""产品文档栏目 API 路由（deepDDW 开源裁剪版）。

端点（13 个）：
  健康：GET    /health
  目录：GET    /categories  POST /categories  PATCH /categories/{id}
  文档：GET    /docs  GET /docs/{id}  POST /docs  PATCH /docs/{id}
        POST /docs/{id}/publish  POST /docs/{id}/archive
  检索：GET    /search?q=&top_k=
  离线：POST   /export  POST /import

鉴权：全部业务端点走网关 Token 门禁（Bearer / X-DDW-Token，缺失/无效 → 401）。
单用户模型：token 持有者即管理员；无租户过滤（tenant_id 恒 0）。
"""
from __future__ import annotations

import logging
from typing import Optional

from core.database.session import session_scope
from core.security.token_gate import require_access_token
from fastapi import APIRouter, Depends, Query

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
    async def list_categories(user: dict = Depends(require_access_token)) -> list:
        """目录树（登录可见）。"""
        async with session_scope() as db:
            svc = DocsPortalService(db)
            return await svc.list_categories_tree(user)

    @router.post("/categories", status_code=201)
    async def create_category(
        data: CategoryCreateReq, user: dict = Depends(require_access_token)
    ) -> dict:
        """建分类（管理员）。"""
        async with session_scope() as db:
            svc = DocsPortalService(db)
            return await svc.create_category(data, user)

    @router.patch("/categories/{category_id}")
    async def update_category(
        category_id: int,
        data: CategoryUpdateReq,
        user: dict = Depends(require_access_token),
    ) -> dict:
        """改分类（管理员）。"""
        async with session_scope() as db:
            svc = DocsPortalService(db)
            return await svc.update_category(category_id, data, user)

    # ─── 文档 ──────────────────────────────────────────────────

    @router.get("/docs", response_model=dict)
    async def list_docs(
        category_id: Optional[int] = Query(None, description="目录过滤"),
        doc_type: Optional[str] = Query(None, description="类型过滤"),
        visibility: Optional[str] = Query(None, description="可见性过滤"),
        workspace: Optional[str] = Query(None, max_length=32,
                                         description="工作区过滤（默认全部；非 shared 按 slug 前缀 ws-{workspace}- 过滤）"),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        user: dict = Depends(require_access_token),
    ) -> dict:
        """文档列表（只返回当前用户可见文档）。

        P1-1（multidevice）：workspace 过滤——非 shared 时仅返回
        category 以 ``ws:{workspace}:`` 开头的文档；shared/None 与旧行为一致。
        """
        async with session_scope() as db:
            svc = DocsPortalService(db)
            return await svc.list_docs(
                user, category_id=category_id, doc_type=doc_type,
                visibility=visibility, workspace=workspace,
                page=page, page_size=page_size,
            )

    @router.get("/docs/{doc_id}")
    async def get_doc(doc_id: int, user: dict = Depends(require_access_token)) -> dict:
        """文档详情（元数据 + 内联正文）。"""
        async with session_scope() as db:
            svc = DocsPortalService(db)
            return await svc.get_doc(doc_id, user)

    @router.post("/docs", status_code=201)
    async def create_doc(
        data: DocCreateReq, user: dict = Depends(require_access_token)
    ) -> dict:
        """新建文档（正文内联存储）。"""
        async with session_scope() as db:
            svc = DocsPortalService(db)
            return await svc.create_doc(data, user)

    @router.patch("/docs/{doc_id}")
    async def update_doc(
        doc_id: int, data: DocUpdateReq, user: dict = Depends(require_access_token)
    ) -> dict:
        """更新文档（version 递增 → DocVersion 记录）。"""
        async with session_scope() as db:
            svc = DocsPortalService(db)
            return await svc.update_doc(doc_id, data, user)

    @router.post("/docs/{doc_id}/publish")
    async def publish_doc(
        doc_id: int, user: dict = Depends(require_access_token)
    ) -> dict:
        """发布（draft→published；写 deepDDW 记忆，失败不阻塞）。"""
        async with session_scope() as db:
            svc = DocsPortalService(db)
            return await svc.publish_doc(doc_id, user)

    @router.post("/docs/{doc_id}/archive")
    async def archive_doc(
        doc_id: int, user: dict = Depends(require_access_token)
    ) -> dict:
        """归档（published→archived；记忆标记 archived 不删除）。"""
        async with session_scope() as db:
            svc = DocsPortalService(db)
            return await svc.archive_doc(doc_id, user)

    # ─── 检索（统一入口） ───────────────────────────────────────

    @router.get("/search")
    async def search_docs(
        q: str = Query(..., min_length=1, max_length=400, description="检索词"),
        top_k: int = Query(5, ge=1, le=20),
        user: dict = Depends(require_access_token),
    ) -> dict:
        """本地关键词检索（只搜 published + 当前用户可见）。"""
        async with session_scope() as db:
            svc = DocsPortalService(db)
            return await svc.search_docs(q, top_k, user)

    # ─── 离线部署包 ─────────────────────────────────────────────

    @router.post("/export")
    async def export_package(user: dict = Depends(require_access_token)) -> dict:
        """导出发布快照（manifest + content_hash，管理员）。"""
        async with session_scope() as db:
            svc = DocsPortalService(db)
            return await svc.export_package(user)

    @router.post("/import")
    async def import_package(
        data: ImportPackageReq, user: dict = Depends(require_access_token)
    ) -> dict:
        """导入离线更新包（按 content_hash 去重幂等，管理员）。"""
        async with session_scope() as db:
            svc = DocsPortalService(db)
            return await svc.import_package(data, user)

    return router


__all__ = ["build_router"]
