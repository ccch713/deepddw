"""DDW SearXNG 插件 API 路由。

端点：
- GET /search  （Depends(current_user)）
- GET /health  （Depends(current_user)）
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from core.auth.jwt import current_user

from . import PLUGIN_NAME
from .schemas import HealthResp, SearchResp
from .services import SearXNGUnavailable, search
from .services import health as health_check

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    router = APIRouter(
        prefix=f"/api/v1/plugins/{PLUGIN_NAME}",
        tags=[PLUGIN_NAME],
    )

    @router.get("/search", response_model=SearchResp)
    async def search_endpoint(
        q: str = Query(..., min_length=1, description="搜索关键词"),
        limit: int = Query(5, ge=1, le=20, description="返回条数"),
        engines: str = Query(None, description="引擎列表，逗号分隔"),
        _user: dict = Depends(current_user),
    ) -> SearchResp:
        try:
            result = await search(q, limit=limit, engines=engines)
            return SearchResp(
                success=True,
                data=result["data"],
                total=result["total"],
                elapsed_ms=result["elapsed_ms"],
                unresponsive_engines=result["unresponsive_engines"],
            )
        except SearXNGUnavailable as e:
            return SearchResp(success=False, error="SEARXNG_UNREACHABLE", detail=str(e))

    @router.get("/health", response_model=HealthResp)
    async def health_endpoint(
        _user: dict = Depends(current_user),
    ) -> HealthResp:
        result = await health_check()
        return HealthResp(**result)

    return router


__all__ = ["build_router"]
