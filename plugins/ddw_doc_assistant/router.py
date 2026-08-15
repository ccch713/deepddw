"""Doc Assistant API Router.

端点：
- POST   /documents/upload       — 上传文档（解析→分块→embedding→向量存储）
- GET    /documents              — 文档列表（按部门筛选）
- DELETE /documents/{id}         — 删除文档及索引
- POST   /documents/query        — RAG 文档问答
- GET    /documents/{id}/chunks  — 文档分块详情
- GET    /health                 — 健康检查
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Request, Response
from pydantic import BaseModel

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter, get_tenant_context

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Doc Assistant"])

# ─── 模块级单例（向量库）───
_vector_store = None
_vector_store_path: Optional[Path] = None


def set_vector_store_path(path: Path) -> None:
    """插件启动时注入向量库路径。"""
    global _vector_store, _vector_store_path
    _vector_store_path = path
    _vector_store = None


def _get_vector_store():
    global _vector_store
    if _vector_store is None:
        from plugins.ddw_knowledge_hierarchy.services.vector_store import VectorStore

        path = _vector_store_path or (
            Path(__file__).resolve().parent / "data" / "da_vector.db"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        _vector_store = VectorStore(str(path))
    return _vector_store


def _get_llm_chat_fn():
    """从平台 LLM 网关获取对话函数；不可用时返回 None。"""
    try:
        from core.llm_gateway.base import ChatMessage
        from core.llm_gateway.gateway import chat as gateway_chat

        async def _chat(prompt: str, system: str = "") -> Optional[str]:
            msgs = []
            if system:
                msgs.append(ChatMessage(role="system", content=system[:2000]))
            msgs.append(ChatMessage(role="user", content=prompt[:3000]))
            resp = await gateway_chat(msgs, max_tokens=1024, temperature=0.2)
            if resp and resp.content and resp.finish_reason != "error":
                return resp.content.strip()
            return None

        return _chat
    except Exception as exc:  # noqa: BLE001
        logger.warning("doc_assistant: LLM gateway unavailable (%s)", exc)
        return None


# ─── 响应模型 ───

from .models import (
    ChunkSchema,
    DocAnswer,
    DocQueryRequest,
    DocSchema,
    SourceChunk,
    UploadResponse,
)


# ─── 端点 ───


@router.post("/documents/upload", response_model=UploadResponse, status_code=201)
async def upload_document(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    uploader: str = Form(""),
    department: str = Form(""),
):
    """上传文档并自动解析、分块、入库。"""
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
    from .service import DocAssistantService

    tenant_id = get_tenant_context() or 0
    suffix = Path(file.filename or "upload").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        async with session_scope() as s, bypass_tenant_filter():
            svc = DocAssistantService(
                db=s,
                vector_store=_get_vector_store(),
                llm_chat_fn=_get_llm_chat_fn(),
            )
            doc = await svc.ingest_document(
                tmp_path,
                title=file.filename,
                uploader=uploader,
                department=department,
                tenant_id=tenant_id,
            )
            await s.refresh(doc)
            doc_id = str(doc.id)
            await s.commit()
            return UploadResponse(
                id=doc_id,
                title=doc.title,
                file_type=doc.file_type,
                file_size=doc.file_size,
                chunk_count=doc.chunk_count,
                vector_indexed=doc.vector_indexed,
            )
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/documents", response_model=List[DocSchema])
async def list_documents(
    department: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    """文档列表（按部门筛选，分页）。"""
    from .service import DocAssistantService

    async with session_scope() as s, bypass_tenant_filter():
        svc = DocAssistantService(
            db=s,
            vector_store=_get_vector_store(),
            llm_chat_fn=None,
        )
        docs = await svc.list_documents(
            department=department, page=page, page_size=page_size
        )
        return [
            DocSchema(
                id=str(d.id),
                title=d.title,
                file_type=d.file_type,
                file_size=d.file_size,
                uploader=d.uploader or "",
                department=d.department or "",
                chunk_count=d.chunk_count,
                vector_indexed=d.vector_indexed,
                created_at=d.created_at.isoformat() if d.created_at else "",
            )
            for d in docs
        ]


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(doc_id: str):
    """删除文档及所有索引数据。"""
    from .service import DocAssistantService

    tenant_id = get_tenant_context() or 0
    async with session_scope() as s, bypass_tenant_filter():
        svc = DocAssistantService(
            db=s,
            vector_store=_get_vector_store(),
            llm_chat_fn=None,
        )
        ok = await svc.delete_document(doc_id, tenant_id=tenant_id)
        if not ok:
            raise HTTPException(404, "文档不存在")
        await s.commit()


@router.post("/documents/query", response_model=DocAnswer)
async def query_documents(req: DocQueryRequest):
    """基于知识库的 RAG 文档问答。"""
    from .service import DocAssistantService

    tenant_id = get_tenant_context() or 0
    async with session_scope() as s, bypass_tenant_filter():
        svc = DocAssistantService(
            db=s,
            vector_store=_get_vector_store(),
            llm_chat_fn=_get_llm_chat_fn(),
        )
        result = await svc.query(
            req.question,
            doc_ids=req.doc_ids or None,
            top_k=req.top_k,
            tenant_id=tenant_id,
        )
        await s.commit()
        return DocAnswer(
            answer=result["answer"],
            sources=[SourceChunk(**src) for src in result["sources"]],
            doc_ids_queried=result["doc_ids_queried"],
        )


@router.get("/documents/{doc_id}/chunks", response_model=List[ChunkSchema])
async def get_document_chunks(doc_id: str):
    """获取文档的分块详情。"""
    from sqlalchemy import select

    from .models import DocMeta
    from .service import DocAssistantService

    async with session_scope() as s, bypass_tenant_filter():
        # 验证文档存在
        doc = (
            await s.execute(select(DocMeta).where(DocMeta.id == doc_id))
        ).scalar_one_or_none()
        if doc is None:
            raise HTTPException(404, "文档不存在")

        svc = DocAssistantService(
            db=s,
            vector_store=_get_vector_store(),
            llm_chat_fn=None,
        )
        chunks = await svc.get_document_chunks(doc_id)
        return [ChunkSchema(**c) for c in chunks]


@router.get("/health")
async def health():
    """健康检查。"""
    from . import PLUGIN_NAME, PLUGIN_VERSION

    vs = _get_vector_store()
    return {
        "plugin": PLUGIN_NAME,
        "status": "ok",
        "version": PLUGIN_VERSION,
        "vector_store": "ready" if vs is not None else "uninitialized",
        "endpoints": [
            "/documents/upload",
            "/documents",
            "/documents/{id}",
            "/documents/query",
            "/documents/{id}/chunks",
        ],
    }
