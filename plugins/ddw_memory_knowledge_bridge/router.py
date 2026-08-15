"""API 路由 — 统一检索 + 双向归档（真实调用 ddw-knowledge-hierarchy API）。"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request, Response
from sqlalchemy import select

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter

from .models import (
    KnowledgeToMemoryReq,
    MemoryToKnowledgeReq,
    UnifiedSearchReq,
)
from .service import (
    archive_memories_to_knowledge,
    import_knowledge_to_memory,
    unified_search,
)

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/plugins/ddw-memory-knowledge-bridge", tags=["bridge"])

    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-memory-knowledge-bridge", "version": "1.0.0", "status": "ok"}

    # ── 真实 KB API 辅助函数 ────────────────────────────────

    async def _kb_get_document(doc_id: str) -> dict | None:
        """从 ddw-knowledge-hierarchy 真实读取文档内容。"""
        from plugins.ddw_knowledge_hierarchy.models import DocumentChunk, KBDocument

        async with session_scope() as s, bypass_tenant_filter():
            # 先查 KBDocument 元数据
            kb_doc = None
            if doc_id.isdigit():
                kb_doc = (await s.execute(
                    select(KBDocument).where(KBDocument.id == int(doc_id))
                )).scalar_one_or_none()

            # 查 DocumentChunk 内容（用 content_ref 或直接 document_id）
            actual_doc_id = kb_doc.content_ref if kb_doc and kb_doc.content_ref else doc_id
            chunks = (await s.execute(
                select(DocumentChunk.content)
                .where(DocumentChunk.document_id == actual_doc_id)
                .order_by(DocumentChunk.chunk_index)
            )).scalars().all()

            if not chunks:
                return None

            title = kb_doc.filename if kb_doc else f"文档#{doc_id}"
            content = "\n\n".join(chunks)
            return {"title": title, "content": content, "doc_id": doc_id}

    async def _kb_upload_document(content: str, title: str, bucket: str, tags: list[str], tenant_id: int, user_id: int) -> dict:
        """向 ddw-knowledge-hierarchy 真实写入文档。"""
        from plugins.ddw_knowledge_hierarchy.models import DocumentChunk, KBDocument

        async with session_scope() as s, bypass_tenant_filter():
            # 创建 KBDocument 记录
            doc = KBDocument(
                kb_id=1,  # 默认 KB；生产应按 bucket 映射
                tenant_id=tenant_id,
                filename=title,
                file_type="md",
                file_size=len(content.encode()),
                chunk_count=1,
                status="indexed",
                uploaded_by=user_id,
            )
            s.add(doc)
            await s.flush()

            # 创建 DocumentChunk
            chunk = DocumentChunk(
                document_id=str(doc.id),
                content=content,
                content_hash=str(hash(content)),
                token_count=len(content) // 2,  # 粗估
                chunk_index=0,
            )
            s.add(chunk)
            await s.flush()
            await s.commit()

            return {"id": str(doc.id), "filename": title}

    async def _kb_search(query: str, tenant_id: int, top_k: int = 10) -> list[dict]:
        """从 ddw-knowledge-hierarchy 真实检索文档 chunks。"""
        from plugins.ddw_knowledge_hierarchy.models import DocumentChunk, KBDocument

        async with session_scope() as s, bypass_tenant_filter():
            # LIKE 检索（向量检索需 vector_store，这里用关键词兜底）
            chunks = (await s.execute(
                select(DocumentChunk)
                .where(DocumentChunk.content.ilike(f"%{query}%"))
                .limit(top_k)
            )).scalars().all()

            results = []
            for chunk in chunks:
                # 查关联的 KBDocument 获取文件名
                doc_title = f"文档#{chunk.document_id}"
                if chunk.document_id and chunk.document_id.isdigit():
                    kb_doc = (await s.execute(
                        select(KBDocument.filename).where(KBDocument.id == int(chunk.document_id))
                    )).scalar_one_or_none()
                    if kb_doc:
                        doc_title = kb_doc

                results.append({
                    "id": chunk.document_id,
                    "content": chunk.content[:500],
                    "score": 0.8,  # LIKE 匹配给固定分
                    "doc_title": doc_title,
                    "created_at": str(chunk.created_at) if chunk.created_at else None,
                })
            return results

    # ── 统一检索 ────────────────────────────────────────────

    @router.post("/search/unified")
    async def search_unified(data: UnifiedSearchReq, tenant_id: int = Query(1)) -> dict:
        """记忆 ∪ 知识库联合检索。"""

        async def _memory_search(**kwargs):
            from plugins.ddw_memory.models import MemoryLayer
            from plugins.ddw_memory.service import MemoryService
            svc = MemoryService()
            layers = [MemoryLayer(val) for val in kwargs.get("layers", []) if val in [e.value for e in MemoryLayer]]
            result = await svc.search_memories(
                tenant_id=kwargs["tenant_id"],
                query=kwargs["query"],
                user_id=kwargs["user_id"],
                layers=layers or None,
                top_k=kwargs.get("top_k", 10),
            )
            return [
                {
                    "id": h.entry.id,
                    "content": h.entry.content,
                    "summary": h.entry.summary,
                    "score": h.score,
                    "layer": h.entry.layer.value,
                    "created_at": h.entry.created_at,
                }
                for h in result.hits
            ]

        async def _knowledge_search(**kwargs):
            return await _kb_search(
                query=kwargs["query"],
                tenant_id=tenant_id,
                top_k=kwargs.get("top_k", 10),
            )

        result = await unified_search(
            tenant_id=tenant_id,
            req=data,
            memory_search_fn=_memory_search,
            knowledge_search_fn=_knowledge_search,
        )
        return result.model_dump(mode="json")

    # ── 记忆 → 知识库归档 ──────────────────────────────────

    @router.post("/archive/memory-to-knowledge")
    async def archive_to_knowledge(data: MemoryToKnowledgeReq, tenant_id: int = Query(1), user_id: int = Query(1)) -> dict:
        """记忆归档到知识库（真实写入）。"""

        async def _memory_get(tid, mid):
            from plugins.ddw_memory.service import MemoryService
            svc = MemoryService()
            entry = await svc.get_memory(tid, mid)
            return entry.model_dump(mode="json") if entry else None

        async def _llm_chat(system, user):
            from core.llm_gateway.base import ChatMessage
            from core.llm_gateway.gateway import chat as gateway_chat
            resp = await gateway_chat([ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)])
            return resp.content

        result = await archive_memories_to_knowledge(
            tenant_id=tenant_id,
            memory_ids=data.memory_ids,
            target_bucket=data.target_bucket,
            auto_classify=data.auto_classify,
            memory_get_fn=_memory_get,
            knowledge_upload_fn=lambda **kw: _kb_upload_document(**kw, tenant_id=tenant_id, user_id=user_id),
            llm_chat_fn=_llm_chat if data.auto_classify else None,
        )
        return result

    # ── 知识库 → 记忆导入 ──────────────────────────────────

    @router.post("/import/knowledge-to-memory")
    async def import_to_memory(
        request: Request, response: Response, data: KnowledgeToMemoryReq,
        tenant_id: int = Query(1), user_id: int = Query(1),
    ) -> dict:
        """知识文档导入为记忆（真实读取 KB）。"""
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


        async def _memory_create(**kwargs):
            from plugins.ddw_memory.models import MemoryLayer
            from plugins.ddw_memory.service import MemoryService
            svc = MemoryService()
            layer = MemoryLayer(kwargs.get("layer", "department"))
            entry = await svc.create_memory(
                tenant_id=kwargs["tenant_id"],
                layer=layer,
                content=kwargs["content"],
                creator_id=user_id,
                tags=kwargs.get("tags", []),
                source_type=kwargs.get("source_type", "import"),
                department_id=kwargs.get("department_id"),
                position_id=kwargs.get("position_id"),
            )
            return entry.model_dump(mode="json")

        async def _llm_chat(system, user):
            from core.llm_gateway.base import ChatMessage
            from core.llm_gateway.gateway import chat as gateway_chat
            resp = await gateway_chat([ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)])
            return resp.content

        result = await import_knowledge_to_memory(
            tenant_id=tenant_id,
            document_ids=data.document_ids,
            target_layer=data.target_layer,
            department_id=data.department_id,
            position_id=data.position_id,
            knowledge_get_fn=_kb_get_document,
            memory_create_fn=_memory_create,
            llm_chat_fn=_llm_chat,
        )
        return result

    # ── 同步状态 ────────────────────────────────────────────

    @router.get("/sync/status")
    async def sync_status() -> dict:
        return {
            "last_memory_to_knowledge_sync": None,
            "last_knowledge_to_memory_sync": None,
            "pending_memory_archives": 0,
            "pending_knowledge_imports": 0,
            "total_synced": 0,
        }

    return router


__all__ = ["build_router"]
