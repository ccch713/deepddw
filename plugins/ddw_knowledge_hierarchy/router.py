"""Knowledge Hierarchy API Router — 接入真实 services 实现（2026-08-08 完成）.

端点：
- POST /documents/upload — 上传文档（解析→分块→embedding→向量存储）
- GET  /documents — 列出文档
- GET  /documents/{document_id} — 文档详情
- DELETE /documents/{document_id} — 删除文档
- POST /search/hierarchical — 层级检索（核心）
- POST /search/flat — 传统平铺检索
- GET  /search/logs — 检索日志
- POST /generate — 生成文档
- GET  /templates — 列出模板
- POST /buckets — 创建知识桶
- GET  /buckets — 列出知识桶
- GET  /health — 健康检查
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter, get_tenant_context

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Knowledge Hierarchy"])

# --------------------------------------------------------------------------- #
# 模块级单例（VectorStore 用独立 SQLite，不依赖平台 DB）
# --------------------------------------------------------------------------- #
_vector_store = None
_vector_store_path: Optional[Path] = None


def set_vector_store_path(path: Path) -> None:
    """插件启动时注入向量库路径（data/kh_vector.db）。"""
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


def _get_llm_chat_fn():
    """从平台 LLM 网关获取对话函数；不可用时返回 None（检索降级为纯向量）。"""
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
        logger.warning("knowledge_hierarchy: LLM gateway unavailable (%s)", exc)
        return None


# ─── 请求/响应模型 ───

class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    knowledge_buckets: List[str] = Field(default=[])
    document_ids: List[str] = Field(default=[])
    max_navigation_nodes: int = Field(default=5, ge=1, le=20)
    max_retrieval_chunks: int = Field(default=10, ge=1, le=50)
    search_mode: str = Field(default="hybrid", pattern="^(hierarchical|flat|hybrid)$")


class GenerateRequest(BaseModel):
    template_name: str = Field(..., description="模板名称: 8d|capa|quality_alert|coa|fmea")
    variables: Dict[str, Any] = Field(default={}, description="模板变量")
    title: Optional[str] = Field(default=None, description="生成文档标题")
    knowledge_bucket: Optional[str] = Field(default=None)
    search_query: Optional[str] = Field(default=None, description="关联检索查询（用于引用知识库）")


class BucketCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = Field(default=None)


class NavigationNodeSchema(BaseModel):
    tree_node_id: str
    title: str
    node_type: str
    node_number: str = ""
    summary: str = ""
    confidence: float = 0.0
    reasoning: str = ""


class RetrievalChunkSchema(BaseModel):
    chunk_id: str
    content: str
    score: float
    section_title: str = ""
    page_number: Optional[int] = None


class SearchResultSchema(BaseModel):
    query: str
    search_mode: str
    total_duration_ms: int = 0
    navigation_nodes: List[NavigationNodeSchema] = []
    retrieval_chunks: List[RetrievalChunkSchema] = []
    answer: str = ""
    cited_sources: List[Dict[str, Any]] = []
    log_id: str = ""


class DocumentSchema(BaseModel):
    id: str
    title: str
    file_type: str
    file_size: int
    knowledge_bucket: str
    hierarchy_indexed: bool
    vector_indexed: bool
    created_at: str


# ─── 依赖注入 ───

def _get_retriever():
    """延迟导入，避免循环依赖。"""
    from .services import HierarchicalRetriever
    return HierarchicalRetriever


# ─── 文档管理 ───

@router.post("/documents/upload", response_model=DocumentSchema, status_code=201)
async def upload_document(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    knowledge_bucket: str = Form("default"),
    access_level: str = Form("internal"),
    auto_index: bool = Form(True),
):
    """上传文档并自动索引（解析→分块→embedding→向量存储）。"""
    # P2 数据同步授权校验：旧码超 7 天倒计时 → 拒绝同步（复制克隆容器失效）。
    # P3 加固：请求方可携带 X-DDW-License-Key（同步方的授权码），由主系统
    # 权威判定该码是否已被替换（删除本机 license_state.json 无法绕过）。
    # P4 捎带：响应头携带本机 state 版本与 superseded 状态（同步通道感知授权
    # 是否已更新；其余拦截点按此模板接入）。
    from core.utils.license_broker import state_version
    from core.utils.license_state import check_sync_allowed, load_license_state

    sync_allowed, sync_reason = check_sync_allowed(
        request.headers.get("X-DDW-License-Key")
    )
    _local_state = load_license_state()
    _state_headers = {
        "X-DDW-License-State-Version": state_version(_local_state),
        "X-DDW-License-Superseded": str(
            bool(_local_state.get("superseded_by"))
        ).lower(),
    }
    if not sync_allowed:
        # 注意：FastAPI 的 HTTPException 异常响应不会带注入的 response.headers，
        # 403 必须显式用 JSONResponse 携带捎带头。
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=403,
            content={"detail": sync_reason},
            headers=_state_headers,
        )
    response.headers.update(_state_headers)

    from .services.pipeline import IngestionPipeline

    tenant_id = get_tenant_context() or 0
    suffix = Path(file.filename or "upload").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = Path(tmp.name)

    try:
        async with session_scope() as s, bypass_tenant_filter():
            pipeline = IngestionPipeline(
                db_session=s,
                vector_store=_get_vector_store(),
                llm_chat_fn=_get_llm_chat_fn(),
            )
            doc = await pipeline.ingest(
                file_path=tmp_path,
                tenant_id=tenant_id,
                knowledge_bucket=knowledge_bucket,
                access_level=access_level,
            )
            # server_default 列（created_at）需 refresh 才能读到值
            # 注意：refresh 会丢弃未 flush 的修改，必须先 refresh 再改 title
            await s.refresh(doc)
            # 用原始文件名覆盖临时文件生成的 title
            if file.filename:
                doc.title = file.filename
            await s.flush()
            created_at = doc.created_at.isoformat() if doc.created_at else ""
            doc_id = str(doc.id)
            await s.commit()
            return DocumentSchema(
                id=doc_id,
                title=doc.title,
                file_type=doc.file_type or suffix.lstrip("."),
                file_size=doc.file_size or 0,
                knowledge_bucket=doc.knowledge_bucket or "default",
                hierarchy_indexed=bool(doc.hierarchy_indexed),
                vector_indexed=bool(doc.vector_indexed),
                created_at=created_at,
            )
    finally:
        tmp_path.unlink(missing_ok=True)


@router.get("/documents", response_model=List[DocumentSchema])
async def list_documents(
    knowledge_bucket: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    """列出文档（按知识桶筛选，分页）。"""
    from sqlalchemy import select

    from .models import Document

    async with session_scope() as s, bypass_tenant_filter():
        stmt = (
            select(Document)
            .order_by(Document.created_at.desc())
        )
        if knowledge_bucket:
            stmt = stmt.where(Document.knowledge_bucket == knowledge_bucket)
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = (await s.execute(stmt)).scalars().all()
        return [
            DocumentSchema(
                id=str(d.id),
                title=d.title,
                file_type=d.file_type or "",
                file_size=d.file_size or 0,
                knowledge_bucket=d.knowledge_bucket or "default",
                hierarchy_indexed=bool(d.hierarchy_indexed),
                vector_indexed=bool(d.vector_indexed),
                created_at=d.created_at.isoformat() if d.created_at else "",
            )
            for d in rows
        ]


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str):
    """删除文档及其所有索引数据（树节点+向量chunks）。"""
    from sqlalchemy import delete, select

    from .models import Document, DocumentChunk, TreeNode

    async with session_scope() as s, bypass_tenant_filter():
        doc = (
            await s.execute(select(Document).where(Document.id == document_id))
        ).scalar_one_or_none()
        if doc is None:
            raise HTTPException(404, "文档不存在")
        # 删除向量 chunks
        vs = _get_vector_store()
        try:
            vs.delete_by_doc(0, str(doc.id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("vector delete failed: %s", exc)
        # 删除树节点 + chunks + 文档（级联）
        await s.execute(delete(TreeNode).where(TreeNode.document_id == document_id))
        await s.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        await s.delete(doc)
        await s.commit()


# ─── 检索（核心 API）───

@router.post("/search/hierarchical", response_model=SearchResultSchema)
async def hierarchical_search(req: SearchRequest):
    """层级检索——核心 API（导航→精确检索→回答）。"""
    tenant_id = get_tenant_context() or 0
    retriever_cls = _get_retriever()
    async with session_scope() as s, bypass_tenant_filter():
        retriever = retriever_cls(
            db_session=s,
            vector_store=_get_vector_store(),
            llm_chat_fn=_get_llm_chat_fn(),
        )
        result = await retriever.search(
            query=req.query,
            tenant_id=tenant_id,
            knowledge_buckets=req.knowledge_buckets or None,
            document_ids=req.document_ids or None,
            max_navigation_nodes=req.max_navigation_nodes,
            max_retrieval_chunks=req.max_retrieval_chunks,
            search_mode="hierarchical",
        )
        await s.commit()
        return SearchResultSchema(
            query=req.query,
            search_mode="hierarchical",
            total_duration_ms=result.total_duration_ms,
            navigation_nodes=[
                NavigationNodeSchema(
                    tree_node_id=n.tree_node_id,
                    title=n.title,
                    node_type=n.node_type,
                    node_number=n.node_number or "",
                    summary=n.summary or "",
                    confidence=float(n.confidence or 0.0),
                    reasoning=n.reasoning or "",
                )
                for n in result.navigation_nodes
            ],
            retrieval_chunks=[
                RetrievalChunkSchema(
                    chunk_id=c.chunk_id,
                    content=c.content,
                    score=float(c.score),
                    section_title=c.section_title or "",
                    page_number=c.page_number,
                )
                for c in result.retrieval_chunks
            ],
            answer=result.answer or "",
            cited_sources=result.cited_sources or [],
            log_id=result.log_id or "",
        )


@router.post("/search/flat", response_model=SearchResultSchema)
async def flat_search(req: SearchRequest):
    """传统 flat chunking 搜索（兼容模式）。"""
    tenant_id = get_tenant_context() or 0
    retriever_cls = _get_retriever()
    async with session_scope() as s, bypass_tenant_filter():
        retriever = retriever_cls(
            db_session=s,
            vector_store=_get_vector_store(),
            llm_chat_fn=None,
        )
        result = await retriever.search(
            query=req.query,
            tenant_id=tenant_id,
            knowledge_buckets=req.knowledge_buckets or None,
            document_ids=req.document_ids or None,
            max_retrieval_chunks=req.max_retrieval_chunks,
            search_mode="flat",
        )
        await s.commit()
        return SearchResultSchema(
            query=req.query,
            search_mode="flat",
            total_duration_ms=result.total_duration_ms,
            retrieval_chunks=[
                RetrievalChunkSchema(
                    chunk_id=c.chunk_id,
                    content=c.content,
                    score=float(c.score),
                    section_title=c.section_title or "",
                    page_number=c.page_number,
                )
                for c in result.retrieval_chunks
            ],
        )


@router.get("/search/logs")
async def list_search_logs(page: int = 1, page_size: int = 20):
    """列出检索日志。"""
    from sqlalchemy import select

    from .models import SearchQueryLog

    async with session_scope() as s, bypass_tenant_filter():
        stmt = (
            select(SearchQueryLog)
            .order_by(SearchQueryLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = (await s.execute(stmt)).scalars().all()
        return [
            {
                "id": str(r.id),
                "query": r.query,
                "final_answer": (r.final_answer or "")[:200],
                "total_duration_ms": (
                    (r.navigation_duration_ms or 0)
                    + (r.retrieval_duration_ms or 0)
                    + (r.answer_duration_ms or 0)
                ),
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]


# ─── 文档生成 ───

@router.post("/generate")
async def generate_document(req: GenerateRequest):
    """基于模板 + 知识库生成文档（8d/capa/quality_alert/coa/fmea）。"""
    from .services.doc_generator import DocumentGenerator

    knowledge_refs = None
    # 有关联检索查询时，先用 flat 检索获取知识引用
    if req.search_query:
        tenant_id = get_tenant_context() or 0
        retriever_cls = _get_retriever()
        async with session_scope() as s, bypass_tenant_filter():
            retriever = retriever_cls(
                db_session=s,
                vector_store=_get_vector_store(),
                llm_chat_fn=None,
            )
            result = await retriever.search(
                query=req.search_query,
                tenant_id=tenant_id,
                knowledge_buckets=[req.knowledge_bucket] if req.knowledge_bucket else None,
                max_retrieval_chunks=5,
                search_mode="flat",
            )
            knowledge_refs = result.retrieval_chunks

    async with session_scope() as s, bypass_tenant_filter():
        gen = DocumentGenerator(db_session=s)
        await gen.init_builtin_templates()
        doc = await gen.generate(
            template_name=req.template_name,
            variables=req.variables,
            knowledge_refs=knowledge_refs,
            title=req.title,
            knowledge_bucket=req.knowledge_bucket,
        )
        await s.commit()
        return {
            "id": str(doc.id),
            "title": doc.title,
            "content": doc.content,
            "doc_type": doc.doc_type,
            "template_id": str(doc.template_id) if doc.template_id else None,
        }


# ─── 模板管理 ───

@router.get("/templates")
async def list_templates():
    """列出所有可用模板。"""
    from .services.doc_generator import BUILTIN_TEMPLATES
    return [
        {
            "name": k,
            "template_type": v["template_type"],
            "industry": v["industry"],
            "description": v["description"],
        }
        for k, v in BUILTIN_TEMPLATES.items()
    ]


# ─── 知识桶 ───

@router.post("/buckets", status_code=201)
async def create_bucket(req: BucketCreateRequest):
    """创建知识桶。"""
    from sqlalchemy import select

    from .models import KnowledgeBucket

    async with session_scope() as s, bypass_tenant_filter():
        existing = (
            await s.execute(
                select(KnowledgeBucket).where(KnowledgeBucket.name == req.name)
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(409, f"知识桶已存在: {req.name}")
        bucket = KnowledgeBucket(name=req.name, description=req.description)
        s.add(bucket)
        await s.commit()
        return {
            "id": str(bucket.id),
            "name": bucket.name,
            "description": bucket.description,
        }


@router.get("/buckets")
async def list_buckets():
    """列出知识桶。"""
    from sqlalchemy import select

    from .models import KnowledgeBucket

    async with session_scope() as s, bypass_tenant_filter():
        rows = (await s.execute(select(KnowledgeBucket))).scalars().all()
        return [
            {
                "id": str(b.id),
                "name": b.name,
                "description": b.description,
                "created_at": b.created_at.isoformat() if b.created_at else "",
            }
            for b in rows
        ]


# ─── 健康检查 ───

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
            "/documents/upload", "/documents",
            "/search/hierarchical", "/search/flat",
            "/generate", "/templates", "/buckets",
        ],
    }
