"""Knowledge Base three-layer permission router (company / department / personal).

Endpoints:
- GET    /kb                  → list knowledge bases (ACL filtered)
- POST   /kb                  → create knowledge base
- GET    /kb/{kb_id}          → get knowledge base + documents
- DELETE /kb/{kb_id}          → delete knowledge base
- POST   /kb/{kb_id}/documents → upload document to KB
- DELETE /kb/{kb_id}/documents/{doc_id} → delete document from KB
- POST   /kb/search           → search across visible KBs
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .acl import Principal, can_delete_kb, can_manage, can_view, visible_kb_filter
from .deps import get_principal
from .models import KBDocument, KnowledgeBase

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Knowledge Base"])

# --------------------------------------------------------------------------- #
# 模块级单例：VectorStore（kb/search 集成真向量检索用 — 2026-08-11）
# --------------------------------------------------------------------------- #
_vector_store = None
_vector_store_path: Path | None = None


def set_vector_store_path(path: Path) -> None:
    """插件启动时注入向量库路径（与 router.py 共享或独立 data/kh_vector.db）。"""
    global _vector_store, _vector_store_path
    _vector_store_path = path
    _vector_store = None


def _get_vector_store():
    global _vector_store
    if _vector_store is None:
        from .services.vector_store import VectorStore

        path = _vector_store_path or (
            Path(__file__).resolve().parent / "data" / "kh_vector.db"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        _vector_store = VectorStore(str(path))
    return _vector_store


# ─── Request / Response schemas ───


class KBCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    scope: str = Field(default="company", pattern="^(company|department|personal)$")
    scope_id: int | None = Field(default=None)
    department_id: int | None = Field(default=None)


class KBSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    scopes: list[str] = Field(default=["company", "department", "personal"])
    search_mode: str = Field(default="flat", pattern="^(flat|hybrid|hierarchical)$")
    max_chunks: int = Field(default=10, ge=1, le=50)


class KBResponse(BaseModel):
    id: int
    name: str
    description: str
    scope: str
    scope_id: int | None = None
    department_id: int | None = None
    owner_id: int
    doc_count: int
    chunk_count: int
    status: str
    created_at: str


class KBDetailResponse(KBResponse):
    documents: list[KBDocResponse] = []


class KBDocResponse(BaseModel):
    id: int
    kb_id: int
    filename: str
    file_type: str
    file_size: int
    chunk_count: int
    status: str
    uploaded_by: int
    created_at: str


# ─── Helpers ───


def _kb_to_resp(kb: KnowledgeBase) -> KBResponse:
    return KBResponse(
        id=kb.id,
        name=kb.name,
        description=kb.description or "",
        scope=kb.scope,
        scope_id=kb.scope_id,
        department_id=kb.department_id,
        owner_id=kb.owner_id,
        doc_count=kb.doc_count,
        chunk_count=kb.chunk_count,
        status=kb.status,
        created_at=kb.created_at.isoformat() if kb.created_at else "",
    )


def _doc_to_resp(doc: KBDocument) -> KBDocResponse:
    return KBDocResponse(
        id=doc.id,
        kb_id=doc.kb_id,
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        chunk_count=doc.chunk_count,
        status=doc.status,
        uploaded_by=doc.uploaded_by,
        created_at=doc.created_at.isoformat() if doc.created_at else "",
    )


# ─── Endpoints ───


@router.get("/kb", response_model=list[KBResponse])
async def list_kbs(
    principal: Principal = Depends(get_principal),
):
    """List knowledge bases visible to the current principal (ACL filtered)."""
    async with session_scope() as s, bypass_tenant_filter():
        clauses = visible_kb_filter(principal)
        stmt = (
            select(KnowledgeBase)
            .where(*clauses)
            .where(KnowledgeBase.status == "active")
            .order_by(KnowledgeBase.created_at.desc())
        )
        rows = (await s.execute(stmt)).scalars().all()
        return [_kb_to_resp(kb) for kb in rows]


@router.post("/kb", response_model=KBResponse, status_code=201)
async def create_kb(
    req: KBCreateRequest,
    principal: Principal = Depends(get_principal),
):
    """Create a new knowledge base."""
    async with session_scope() as s, bypass_tenant_filter():
        kb = KnowledgeBase(
            tenant_id=principal.tenant_id,
            name=req.name,
            description=req.description,
            scope=req.scope,
            scope_id=req.scope_id,
            department_id=req.department_id,
            owner_id=principal.user_id,
        )
        s.add(kb)
        await s.flush()
        resp = _kb_to_resp(kb)
        await s.commit()
        return resp


async def _get_kb_with_acl(
    s, kb_id: int, principal: Principal, *, require_manage: bool = False
) -> KnowledgeBase:
    """Fetch a KB and verify ACL. Raises 404/403 as needed."""
    kb = (
        await s.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id == kb_id,
                KnowledgeBase.status == "active",
            )
        )
    ).scalar_one_or_none()
    if kb is None:
        raise HTTPException(404, "知识库不存在")
    if not can_view(kb, principal):
        raise HTTPException(403, "无权访问此知识库")
    if require_manage and not can_manage(kb, principal):
        raise HTTPException(403, "无权管理此知识库")
    return kb


@router.get("/kb/{kb_id}", response_model=KBDetailResponse)
async def get_kb(
    kb_id: int,
    principal: Principal = Depends(get_principal),
):
    """Get a knowledge base and its documents."""
    async with session_scope() as s, bypass_tenant_filter():
        kb = await _get_kb_with_acl(s, kb_id, principal)
        docs = (
            await s.execute(
                select(KBDocument)
                .where(KBDocument.kb_id == kb_id)
                .order_by(KBDocument.created_at.desc())
            )
        ).scalars().all()
        resp = KBDetailResponse(**_kb_to_resp(kb).model_dump())
        resp.documents = [_doc_to_resp(d) for d in docs]
        return resp


@router.delete("/kb/{kb_id}", status_code=204)
async def delete_kb(
    kb_id: int,
    principal: Principal = Depends(get_principal),
):
    """Delete a knowledge base (owner only, or dept_admin for department KBs)."""
    async with session_scope() as s, bypass_tenant_filter():
        kb = (
            await s.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.id == kb_id,
                    KnowledgeBase.status == "active",
                )
            )
        ).scalar_one_or_none()
        if kb is None:
            raise HTTPException(404, "知识库不存在")
        if not can_delete_kb(kb, principal):
            raise HTTPException(403, "无权删除此知识库")
        # Delete documents first, then KB
        await s.execute(delete(KBDocument).where(KBDocument.kb_id == kb_id))
        await s.delete(kb)
        await s.commit()


@router.post("/kb/{kb_id}/documents", response_model=KBDocResponse, status_code=201)
async def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    principal: Principal = Depends(get_principal),
):
    """Upload a document to a knowledge base (requires manage permission).

    保存文件内容并生成 kh_documents/kh_chunks（供蒸馏引擎与检索使用），
    将生成的 kh_document.id 记录到 KBDocument.content_ref。
    """
    import shutil
    import tempfile
    from pathlib import Path

    async with session_scope() as s, bypass_tenant_filter():
        kb = await _get_kb_with_acl(s, kb_id, principal, require_manage=True)
        filename = file.filename or "unnamed"
        suffix = Path(filename).suffix

        # 1. 保存上传文件到临时位置
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = Path(tmp.name)

        content_ref = None
        try:
            # 2. 走 IngestionPipeline 生成 kh_documents + kh_chunks（解析→分块→embedding）
            from .router import _get_llm_chat_fn, _get_vector_store
            from .services.pipeline import IngestionPipeline

            pipeline = IngestionPipeline(
                db_session=s,
                vector_store=_get_vector_store(),
                llm_chat_fn=_get_llm_chat_fn(),
            )
            kh_doc = await pipeline.ingest(
                file_path=tmp_path,
                tenant_id=principal.tenant_id,
                knowledge_bucket=f"kb-{kb_id}",
                access_level="internal",
            )
            await s.flush()
            content_ref = str(kh_doc.id)

            # 3. 创建 KBDocument 记录
            doc = KBDocument(
                kb_id=kb_id,
                tenant_id=principal.tenant_id,
                filename=filename,
                file_type=suffix.lstrip(".") if suffix else "unknown",
                file_size=tmp_path.stat().st_size,
                uploaded_by=principal.user_id,
                content_ref=content_ref,
                chunk_count=0,
            )
            s.add(doc)
            kb.doc_count = (kb.doc_count or 0) + 1
            await s.flush()
            resp = _doc_to_resp(doc)
            await s.commit()
            return resp
        finally:
            tmp_path.unlink(missing_ok=True)


@router.delete("/kb/{kb_id}/documents/{doc_id}", status_code=204)
async def delete_document(
    kb_id: int,
    doc_id: int,
    principal: Principal = Depends(get_principal),
):
    """Delete a document from a knowledge base (requires manage permission)."""
    async with session_scope() as s, bypass_tenant_filter():
        kb = await _get_kb_with_acl(s, kb_id, principal, require_manage=True)
        doc = (
            await s.execute(
                select(KBDocument).where(
                    KBDocument.id == doc_id,
                    KBDocument.kb_id == kb_id,
                )
            )
        ).scalar_one_or_none()
        if doc is None:
            raise HTTPException(404, "文档不存在")
        await s.delete(doc)
        kb.doc_count = max(0, (kb.doc_count or 1) - 1)
        await s.commit()


@router.post("/kb/search")
async def search_kbs(
    req: KBSearchRequest,
    principal: Principal = Depends(get_principal),
):
    """Search across visible knowledge bases.

    流程（2026-08-11 升级）：
    1. ACL 过滤可见 KB
    2. 真向量检索（services/kb_vector.search_kb_documents）
       - 成功且有分块 → 返回分块结果（含 score/text_head）
       - 失败 / 向量为空 / 无关联 Document → 优雅降级，返回元数据列表
    """
    async with session_scope() as s, bypass_tenant_filter():
        clauses = visible_kb_filter(principal)
        stmt = (
            select(KnowledgeBase)
            .where(*clauses)
            .where(KnowledgeBase.status == "active")
            .where(KnowledgeBase.scope.in_(req.scopes))
        )
        kbs = (await s.execute(stmt)).scalars().all()
        kb_ids = [kb.id for kb in kbs]
        if not kb_ids:
            return {"query": req.query, "results": [], "total": 0, "mode": req.search_mode}

        # ① 优先调真向量检索；失败时降级
        try:
            from .services.kb_vector import search_kb_documents

            vector_hits = await search_kb_documents(
                db=s,
                query=req.query,
                kb_ids=kb_ids,
                tenant_id=principal.tenant_id,
                vector_store=_get_vector_store(),
                search_mode=req.search_mode,
                max_chunks=req.max_chunks,
            )
            if vector_hits:
                return {
                    "query": req.query,
                    "results": vector_hits,
                    "total": len(vector_hits),
                    "mode": req.search_mode,
                    "source": "vector",
                }
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "kb/search: vector search failed (%s) — falling back to metadata.",
                e,
            )

        # ② 降级：返回元数据列表（旧行为）
        docs_stmt = (
            select(KBDocument)
            .where(KBDocument.kb_id.in_(kb_ids))
            .order_by(KBDocument.created_at.desc())
            .limit(50)
        )
        docs = (await s.execute(docs_stmt)).scalars().all()
        return {
            "query": req.query,
            "results": [
                {
                    "kb_id": d.kb_id,
                    "doc_id": d.id,
                    "filename": d.filename,
                    "file_type": d.file_type,
                    "status": d.status,
                }
                for d in docs
            ],
            "total": len(docs),
            "mode": req.search_mode,
            "source": "metadata_fallback",
        }
