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
    memory_budget_status,
    memory_context_build,
    memory_get,
    memory_log_append,
    memory_logs_recent,
    memory_maintain,
    memory_note_put,
    memory_put,
    memory_reflect_save,
    memory_search,
    memory_search_v2,
    memory_user_put,
    session_doc_add,
    session_docs_list,
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


class SessionDocReq(BaseModel):
    """会话产出文档：入库知识库并关联到 dsh 会话（#6 会话→文档闭环）。"""

    session_id: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., max_length=1_000_000)
    kind: str = Field(default="chat", max_length=32)


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


# ---------------------------------------------------------------------------
# 分层记忆（借鉴 dsh-auto-memory：用户偏好 / 笔记 / 每日日志 / 每日反思）
# ---------------------------------------------------------------------------

class MemoryUserReq(BaseModel):
    key: str = Field(..., min_length=1, max_length=200)
    value: str = Field(..., max_length=200_000)


class MemoryNoteReq(BaseModel):
    key: str = Field(..., min_length=1, max_length=200)
    value: str = Field(..., max_length=200_000)
    source: str = Field(default="deepddw", max_length=40)


class MemoryLogReq(BaseModel):
    content: str = Field(..., min_length=1, max_length=20_000)
    auto: bool = Field(default=False)


class MemoryReflectReq(BaseModel):
    content: str = Field(..., min_length=1, max_length=20_000)
    style: str = Field(default="auto", max_length=20)


@router.post("/memory/user")
async def put_memory_user(
    payload: MemoryUserReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """用户级长期偏好/事实（三层记忆之用户层）。"""
    return ok(memory_user_put(payload.key, payload.value))


@router.post("/memory/notes")
async def put_memory_note(
    payload: MemoryNoteReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """项目笔记（三层记忆之笔记层；先查后插 upsert）。"""
    return ok(memory_note_put(payload.key, payload.value, payload.source))


@router.post("/memory/logs")
async def append_memory_log(
    payload: MemoryLogReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """每日日志（append-only；auto=true 标记为自动沉淀）。"""
    return ok(memory_log_append(payload.content, auto=payload.auto))


@router.get("/memory/logs")
async def recent_memory_logs(
    days: int = Query(3, ge=1, le=30),
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """最近 N 天日志。"""
    return ok(memory_logs_recent(days))


@router.get("/memory/context")
async def memory_context(
    budget: int = Query(2400, ge=200, le=8000),
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """构建注入上下文的记忆块（chat 自动注入同源；可预览）。"""
    return ok(memory_context_build(budget))


@router.post("/memory/reflect")
async def reflect_memory(
    payload: MemoryReflectReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """保存当日反思（同一日期幂等更新）。"""
    return ok(memory_reflect_save(payload.content, payload.style))


@router.get("/memory/budget")
async def memory_budget(
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """当日写预算状态（用户/项目字预算；超限需 AI 压缩或归档）。"""
    return ok(memory_budget_status())


@router.post("/memory/maintain")
async def maintain_memory(
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """超预算归档最旧笔记到 archive（维护钩子）。"""
    return ok(memory_maintain())


@router.get("/memory/search-v2")
async def search_memory_v2(
    q: str = Query(..., min_length=1, max_length=200),
    top_k: int = Query(5, ge=1, le=20),
    expand: bool = Query(True, description="LLM 扩写关键词（失败自动降级原词）"),
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """分层记忆检索（OR 多关键词扫四层，返回 layer/source 标注；LLM 扩写增强）。"""
    if expand:
        from core.knowledge import memory_search_v2_async

        result = await memory_search_v2_async(q, top_k, expand=True)
    else:
        result = memory_search_v2(q, top_k)
    return ok({
        "results": result.get("results", []),
        "layers": result.get("layers", []),
        "expanded": result.get("expanded", []),
        "degraded": result.get("degraded", False),
    })


@router.post("/knowledge/session-docs", status_code=status.HTTP_201_CREATED)
async def add_session_doc(
    payload: SessionDocReq,
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """会话→文档：对话产出的文档入库并关联到 dsh 会话。"""
    result = session_doc_add(payload.session_id, payload.title,
                             payload.content, payload.kind)
    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("note", "写入失败"))
    return ok(result)


@router.get("/knowledge/session-docs")
async def list_session_docs(
    session_id: str = Query(..., min_length=1, max_length=128),
    limit: int = Query(50, ge=1, le=200),
    claims: Dict[str, Any] = Depends(require_access_token),
) -> Dict[str, Any]:
    """按会话列出产出文档（文档栏按当前 dsh 会话过滤）。"""
    result = session_docs_list(session_id, limit)
    return ok({
        "results": result.get("results", []),
        "degraded": result.get("degraded", False),
    })


__all__ = ["router"]
