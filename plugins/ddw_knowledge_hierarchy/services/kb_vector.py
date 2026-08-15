"""KBDocument → Document → 向量检索桥接。

设计要点：
- KBDocument (kh_kb_documents) 与 Document (kh_documents) 之间没有直接外键，
  本模块按 ``filename`` 软匹配（同 KB + 租户内 filename 唯一）。
- 调用方传入 ``HierarchicalRetriever`` 实例，向量为空或无关联 Document 时
  返回空列表，由调用方决定降级（不抛异常）。
- 不直接 import HierarchicalRetriever 的具体实现路径，避免循环；
  调用方注入 retriever 即可。

新增于 TASK_SPEC_D：kb/search 集成真向量检索（2026-08-11）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Document, KBDocument

logger = logging.getLogger(__name__)


async def _resolve_documents(
    db: AsyncSession,
    kb_docs: "list[KBDocument]",
) -> "dict[int, Document]":
    """按 filename 在 Document 表中查找对应 Document。

    返回 ``{kb_doc_id: Document}`` 映射；找不到的 kb_doc_id 不在结果中。
    """
    if not kb_docs:
        return {}

    filenames = list({d.filename for d in kb_docs if d.filename})
    if not filenames:
        return {}

    stmt = select(Document).where(Document.title.in_(filenames))
    rows = (await db.execute(stmt)).scalars().all()
    doc_by_title = {d.title: d for d in rows if d.title}

    mapping: Dict[int, Document] = {}
    for kd in kb_docs:
        if kd.filename and kd.filename in doc_by_title:
            mapping[kd.id] = doc_by_title[kd.filename]
    return mapping


async def search_kb_documents(
    db: AsyncSession,
    query: str,
    kb_ids: List[int],
    tenant_id: int,
    vector_store,
    *,
    search_mode: str = "flat",  # noqa: ARG001 — reserved for future hybrid/hierarchical
    max_chunks: int = 10,
    embedding_service=None,
    llm_chat_fn=None,  # noqa: ARG001 — reserved for hierarchical mode
) -> List[Dict[str, Any]]:
    """对一组 KB 内可见文档做真向量检索。

    Args:
        db: 异步数据库 session。
        query: 用户查询文本。
        kb_ids: 已 ACL 过滤的 KB id 列表。
        tenant_id: 租户 id（向量库租户隔离）。
        vector_store: VectorStore 实例（注入）。
        search_mode: ``flat`` / ``hybrid`` / ``hierarchical``。
        max_chunks: 返回分块上限。
        embedding_service: 可选 EmbeddingService；为 None 时取默认。
        llm_chat_fn: 可选 LLM 聊天函数（hierarchical 模式需用）。

    Returns:
        ``[{kb_id, doc_id, filename, score, text_head, chunk_id, content}, ...]``
        无向量数据 / 无关联 Document 时返回 ``[]``（调用方降级）。
    """
    if not kb_ids or not query.strip():
        return []

    # 1. 取 KB 下 KBDocument
    docs_stmt = (
        select(KBDocument)
        .where(KBDocument.kb_id.in_(kb_ids))
        .where(KBDocument.tenant_id == tenant_id)
        .order_by(KBDocument.created_at.desc())
        .limit(100)
    )
    kb_docs: List[KBDocument] = (await db.execute(docs_stmt)).scalars().all()
    if not kb_docs:
        return []

    # 2. 软匹配 KBDocument → Document
    kd_to_doc = await _resolve_documents(db, kb_docs)
    if not kd_to_doc:
        logger.debug(
            "kb_vector.search_kb_documents: no KBDocument->Document mapping "
            "(kb_ids=%s, tenant=%s) — caller should degrade.",
            kb_ids,
            tenant_id,
        )
        return []

    # 3. 准备 document_ids + 提前检查向量库是否为空
    document_ids = [doc.id for doc in kd_to_doc.values()]

    try:
        if hasattr(vector_store, "count"):
            cnt = vector_store.count(tenant_id=tenant_id)
            if cnt == 0:
                logger.debug(
                    "kb_vector: vector store empty for tenant=%s — degrade.",
                    tenant_id,
                )
                return []
    except Exception as e:  # noqa: BLE001
        logger.warning("kb_vector: vector_store.count failed (%s) — proceed anyway.", e)

    # 4. 直接调 vector_store.search，自己组装 hits（保留 doc_id 字段）
    #    不走 HierarchicalRetriever —— 因为 retriever 不暴露 doc_id，
    #    改 retriever 会违反 TASK_SPEC_D 红线 #2。
    try:
        from .embedding_service import get_default_embedding

        emb = embedding_service or get_default_embedding()
        query_emb = await emb.embed(query)
        hits = vector_store.search(
            tenant_id=tenant_id,
            query_embedding=query_emb,
            top_k=max_chunks,
            doc_ids=document_ids,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("kb_vector: vector_store.search failed (%s) — return empty.", e)
        return []

    # 5. 反查每个 hit 的 doc_id → KBDocument（hit 含 doc_id 字段）
    kd_by_doc_id: Dict[str, KBDocument] = {}
    for kb_doc_id, doc in kd_to_doc.items():
        kd = next((d for d in kb_docs if d.id == kb_doc_id), None)
        if kd is not None:
            kd_by_doc_id[doc.id] = kd

    out: List[Dict[str, Any]] = []
    for hit in hits:
        hit_doc_id = hit.get("doc_id") or hit.get("chunk_id")
        src_kd = kd_by_doc_id.get(hit_doc_id) if hit_doc_id else None
        if src_kd is None:
            continue
        content = hit.get("content", "")
        metadata = hit.get("metadata") or {}
        out.append({
            "kb_id": src_kd.kb_id,
            "doc_id": src_kd.id,
            "filename": src_kd.filename,
            "chunk_id": hit.get("chunk_id", ""),
            "score": float(hit.get("score", 0.0)),
            "text_head": content[:200],
            "content": content,
            "section_title": metadata.get("section_title", ""),
            "page_number": metadata.get("page_number"),
        })

    return out


__all__ = ["search_kb_documents"]