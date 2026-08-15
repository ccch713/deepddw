"""deepDDW 知识库 + 记忆 API（开源裁剪版，真实实现）。

端点（全部走网关 Token 门禁）：
- ``GET  /api/v1/knowledge/search?q=&top_k=``   知识库检索（FTS5/LIKE）
- ``POST /api/v1/knowledge/documents``          新增知识文档
- ``GET  /api/v1/knowledge/bases``              文档列表（标题）
- ``POST /api/v1/memory/put``                   写入记忆
- ``GET  /api/v1/memory/get``                   读取单条记忆
- ``GET  /api/v1/memory/search``                检索记忆

存储：SQLite（ddw_main.db），表 kb_documents / memory_entries。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.api_response import ok
from core.knowledge import (
    kb_add_document,
    kb_search,
    memory_get,
    memory_put,
    memory_search,
)
from core.security.token_gate import require_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["knowledge", "memory"])


class KbDocumentReq(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., max_length=1_000_000)
    category: str = Field(default="public", max_length=40)


class MemoryPutReq(BaseModel):
    namespace: str = Field(default="default", max_length=64)
    key: str = Field(..., min_length=1, max_length=200)
    value: str = Field(..., max_length=200_000)
    tags: List[str] = Field(default_factory=list, max_length=20)


@router.get("/knowledge/search")
async def search_kb(
    q: str = Query(..., min_length=1, max_length=200),
    top_k: int = Query(5, ge=1, le=20),
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    result = kb_search(q, top_k)
    return ok({"results": result.get("results", []), "degraded": result.get("degraded", False)})


@router.post("/knowledge/documents", status_code=status.HTTP_201_CREATED)
async def add_document(payload: KbDocumentReq, claims: Dict[str, Any] = Depends(require_access_token)) -> Dict[str, Any]:
    try:
        doc = kb_add_document(payload.title, payload.content, payload.category)
        return ok(doc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("kb add document failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"写入失败：{exc}") from exc


@router.get("/knowledge/bases")
async def list_documents(claims: Dict[str, Any] = Depends(require_access_token)) -> Dict[str, Any]:
    from core.knowledge import get_conn

    try:
        conn = get_conn()
        try:
            rows = conn.execute(
                "SELECT id, title, category, created_at FROM kb_documents ORDER BY id"
            ).fetchall()
        finally:
            conn.close()
        return ok([dict(r) for r in rows])
    except Exception as exc:  # noqa: BLE001
        logger.warning("kb list degraded: %s", exc)
        return ok([])


@router.post("/memory/put")
async def put_memory(payload: MemoryPutReq, claims: Dict[str, Any] = Depends(require_access_token)) -> Dict[str, Any]:
    result = memory_put(payload.namespace, payload.key, payload.value, payload.tags)
    return ok(result)


@router.get("/memory/get")
async def get_memory(
    key: str = Query(..., min_length=1),
    namespace: str = Query("default", max_length=64),
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    result = memory_get(namespace, key)
    return ok(result)


@router.get("/memory/search")
async def search_memory(
    q: str = Query(..., min_length=1, max_length=200),
    namespace: str = Query("default", max_length=64),
    top_k: int = Query(5, ge=1, le=20),
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    result = memory_search(namespace, q, top_k)
    return ok({"results": result.get("results", []), "degraded": result.get("degraded", False)})


__all__ = ["router"]
