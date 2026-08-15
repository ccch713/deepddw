"""FastAPI 路由：文档管理 + 检索 + 问答（SSE）。"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, File, HTTPException, UploadFile, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func as sqla_func
from sqlalchemy import select

from core.database.session import session_scope

from .core.embedding import create_embedding_service
from .core.vector_store import VectorStore
from .models import Document
from .schemas import (
    ChatRequest,
    DocumentListOut,
    DocumentOut,
    SearchRequest,
    SearchResponse,
)
from .services.ingest_service import IngestService
from .services.retrieval_service import RetrievalService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/plugins/ddw-ent-knowledge", tags=["ddw-ent-knowledge"])

# ---------------------------------------------------------------------------
# 全局单例（lazy init）
# ---------------------------------------------------------------------------

_embedding = None
_vector_store = None
_ingest_service = None
_retrieval_service = None
_DATA_DIR = "./data/kb"


def _get_embedding():
    global _embedding
    if _embedding is None:
        _embedding = create_embedding_service()
    return _embedding


def _get_vector_store():
    global _vector_store
    if _vector_store is None:
        db_path = Path(_DATA_DIR) / "vectors.sqlite"
        _vector_store = VectorStore(db_path)
    return _vector_store


def _get_ingest_service():
    global _ingest_service
    if _ingest_service is None:
        _ingest_service = IngestService(_get_embedding(), _get_vector_store(), _DATA_DIR)
    return _ingest_service


def _get_retrieval_service():
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService(_get_embedding(), _get_vector_store())
    return _retrieval_service


def _reset_services():
    """测试用：重置所有服务单例。"""
    global _embedding, _vector_store, _ingest_service, _retrieval_service
    _embedding = None
    _vector_store = None
    _ingest_service = None
    _retrieval_service = None


# ---------------------------------------------------------------------------
# 文档管理 API
# ---------------------------------------------------------------------------


@router.post("/documents/upload")
async def upload_document(
    request: Request, response: Response, file: UploadFile = File(...)
) -> JSONResponse:
    """上传文档（md/txt/json/yaml/pdf），自动解析入库。"""
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
    if not file.filename:
        raise HTTPException(400, "filename is required")

    data = await file.read()
    if len(data) > 50 * 1024 * 1024:  # 50MB limit
        raise HTTPException(400, "file too large (max 50MB)")

    ingest = _get_ingest_service()
    # MVP: tenant_id=1 固定
    tenant_id = 1

    async with session_scope() as session:
        result = await ingest.ingest_upload(session, tenant_id, file.filename, data)
        await session.commit()

    if result.get("error"):
        return JSONResponse(result, status_code=400)
    return JSONResponse(result, status_code=201)


@router.get("/documents", response_model=DocumentListOut)
async def list_documents(page: int = 1, page_size: int = 20) -> DocumentListOut:
    """文档列表（分页）。"""
    tenant_id = 1
    async with session_scope() as session:
        # Count
        count_q = select(sqla_func.count()).select_from(Document).where(Document.tenant_id == tenant_id)
        total = (await session.execute(count_q)).scalar() or 0

        # Items
        offset = (page - 1) * page_size
        items_q = (
            select(Document)
            .where(Document.tenant_id == tenant_id)
            .order_by(Document.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await session.execute(items_q)).scalars().all()

    items = [
        DocumentOut(
            id=d.id,
            doc_uuid=d.doc_uuid,
            file_name=d.file_name,
            file_type=d.file_type,
            chunk_count=d.chunk_count,
            status=d.status,
            created_at=d.created_at.isoformat() if d.created_at else None,
        )
        for d in rows
    ]
    return DocumentListOut(items=items, total=total)


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int) -> Dict[str, Any]:
    """删除文档及其 chunks。"""
    tenant_id = 1
    ingest = _get_ingest_service()
    async with session_scope() as session:
        deleted = await ingest.delete_document(session, tenant_id, doc_id)
        await session.commit()

    if not deleted:
        raise HTTPException(404, "document not found")
    return {"status": "deleted", "doc_id": doc_id}


# ---------------------------------------------------------------------------
# 检索 API
# ---------------------------------------------------------------------------


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest) -> SearchResponse:
    """语义检索 + BM25 fallback。"""
    tenant_id = 1
    retrieval = _get_retrieval_service()
    result = await retrieval.search(tenant_id, req.query, top_k=req.top_k)
    return SearchResponse(
        hits=result["hits"],
        took_ms=result["took_ms"],
    )


# ---------------------------------------------------------------------------
# 问答 API（SSE 流式）
# ---------------------------------------------------------------------------


@router.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    """检索 top-5 → 组装 context → LLM 生成 → SSE 流式返回。"""
    tenant_id = 1
    retrieval = _get_retrieval_service()

    # 1. 检索
    search_result = await retrieval.search(tenant_id, req.query, top_k=req.top_k)
    kb_took_ms = search_result["took_ms"]
    hits = search_result["hits"]

    # 2. 组装 context
    context_parts = []
    for i, hit in enumerate(hits, 1):
        context_parts.append(f"[{i}] {hit['content'][:600]}")
    context = "\n\n".join(context_parts) if context_parts else "（暂无相关知识）"

    # 3. SSE 流式返回
    async def event_generator():
        t0 = time.time()

        # 先发检索元信息
        meta = {"kb_took_ms": kb_took_ms, "hit_count": len(hits)}
        yield f"data: {json.dumps({'type': 'meta', **meta})}\n\n"

        # 调 LLM Gateway
        try:
            from core.llm_gateway.base import ChatMessage
            from core.llm_gateway.gateway import stream_chat

            system = (
                "你是企业知识库助手。根据以下检索到的知识片段回答用户问题。\n"
                "如果知识片段中没有相关信息，请如实说明。\n\n"
                f"知识片段：\n{context}"
            )
            messages = [
                ChatMessage(role="system", content=system),
                ChatMessage(role="user", content=req.query),
            ]

            full_content = []
            async for chunk in stream_chat(messages, max_tokens=512, temperature=0.6):
                if chunk:
                    full_content.append(chunk)
                    yield f"data: {json.dumps({'type': 'token', 'token': chunk})}\n\n"

            elapsed_ms = int((time.time() - t0) * 1000)
            yield f"data: {json.dumps({'type': 'done', 'elapsed_ms': elapsed_ms})}\n\n"

        except Exception as exc:
            logger.warning("chat LLM failed: %s", exc)
            # 降级：直接返回检索结果
            fallback = hits[0]["content"][:300] if hits else "暂无相关信息"
            yield f"data: {json.dumps({'type': 'token', 'token': fallback})}\n\n"
            elapsed_ms = int((time.time() - t0) * 1000)
            yield f"data: {json.dumps({'type': 'done', 'elapsed_ms': elapsed_ms, 'fallback': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-KB-Took-Ms": str(kb_took_ms),
        },
    )


# ---------------------------------------------------------------------------
# 健康检查
# ---------------------------------------------------------------------------


@router.get("/health")
async def health() -> Dict[str, Any]:
    vs = _get_vector_store()
    return {
        "plugin": "ddw_ent_knowledge",
        "version": "1.0.0",
        "status": "ok",
        "embedding": _get_embedding().name,
        "chunks": vs.count(1),
    }


__all__ = ["router", "_reset_services"]
