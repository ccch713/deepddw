"""桥接核心逻辑 — 统一检索 + 双向归档。不含独立存储，只读写两个插件 API。"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable

from .llm_classify import classify_content, summarize_document
from .models import (
    UnifiedSearchHit,
    UnifiedSearchReq,
    UnifiedSearchResponse,
)

logger = logging.getLogger(__name__)

# 归档批量大小
ARCHIVE_BATCH_SIZE = 10


async def unified_search(
    tenant_id: int,
    req: UnifiedSearchReq,
    memory_search_fn: Callable | None = None,
    knowledge_search_fn: Callable | None = None,
) -> UnifiedSearchResponse:
    """记忆 ∪ 知识库联合检索。

    memory_search_fn: async (tenant_id, query, user_id, layers, top_k) -> list[dict]
    knowledge_search_fn: async (query, top_k) -> list[dict]
    """
    t0 = time.monotonic()
    hits: list[UnifiedSearchHit] = []
    memory_count = 0
    knowledge_count = 0

    # 搜索记忆
    if req.search_memory and memory_search_fn:
        try:
            mem_results = await memory_search_fn(
                tenant_id=tenant_id,
                query=req.query,
                user_id=req.user_id,
                layers=req.memory_layers,
                top_k=req.top_k,
            )
            for item in (mem_results if isinstance(mem_results, list) else []):
                hits.append(UnifiedSearchHit(
                    source="memory",
                    source_id=str(item.get("id", "")),
                    content=item.get("content", ""),
                    summary=item.get("summary"),
                    score=item.get("score", 0.0) * 1.0,
                    layer=item.get("layer"),
                    created_at=item.get("created_at"),
                ))
                memory_count += 1
        except Exception as e:
            logger.warning("memory search failed: %s", e)

    # 搜索知识库
    if req.search_knowledge and knowledge_search_fn:
        try:
            kb_results = await knowledge_search_fn(
                query=req.query,
                top_k=req.top_k,
            )
            for item in (kb_results if isinstance(kb_results, list) else []):
                hits.append(UnifiedSearchHit(
                    source="knowledge",
                    source_id=str(item.get("id", "")),
                    content=item.get("content", ""),
                    summary=item.get("summary"),
                    score=item.get("score", 0.0) * 0.8,
                    doc_title=item.get("doc_title"),
                    created_at=item.get("created_at"),
                ))
                knowledge_count += 1
        except Exception as e:
            logger.warning("knowledge search failed: %s", e)

    # RRF 合并排序
    hits.sort(key=lambda h: h.score, reverse=True)
    hits = hits[:req.top_k]
    took_ms = int((time.monotonic() - t0) * 1000)

    return UnifiedSearchResponse(
        hits=hits,
        total=len(hits),
        memory_count=memory_count,
        knowledge_count=knowledge_count,
        took_ms=took_ms,
    )


async def archive_memories_to_knowledge(
    tenant_id: int,
    memory_ids: list[int],
    target_bucket: str | None,
    auto_classify: bool,
    memory_get_fn: Callable,
    knowledge_upload_fn: Callable,
    llm_chat_fn: Callable | None = None,
    available_buckets: list[str] | None = None,
) -> dict:
    """把记忆条目归档到知识库。

    memory_get_fn: async (tenant_id, memory_id) -> dict
    knowledge_upload_fn: async (content, title, bucket, tags) -> dict
    """
    archived = 0
    failed = 0

    for mem_id in memory_ids:
        try:
            mem = await memory_get_fn(tenant_id, mem_id)
            if not mem:
                failed += 1
                continue

            content = mem.get("content", "")
            tags = mem.get("tags", [])
            layer = mem.get("layer", "personal")

            # 分类
            bucket = target_bucket
            if auto_classify and not bucket and llm_chat_fn:
                classify_result = await classify_content(
                    content=content, tags=tags, layer=layer,
                    available_buckets=available_buckets or [],
                    llm_chat_fn=llm_chat_fn,
                )
                bucket = classify_result.get("suggested_bucket", "")
                tags = tags + classify_result.get("suggested_tags", [])

            # 生成 Markdown 文档
            title = f"[记忆归档] {content[:50]}"
            md_content = f"# {title}\n\n来源：记忆引擎 (ID: {mem_id})\n层级：{layer}\n\n{content}\n\n标签：{', '.join(tags)}"

            await knowledge_upload_fn(
                content=md_content,
                title=title,
                bucket=bucket or "未分类",
                tags=tags + ["archived_from_memory"],
            )
            archived += 1
        except Exception as e:
            logger.warning("archive memory %s failed: %s", mem_id, e)
            failed += 1

    return {"archived": archived, "failed": failed}


async def import_knowledge_to_memory(
    tenant_id: int,
    document_ids: list[str],
    target_layer: str,
    department_id: int | None,
    position_id: int | None,
    knowledge_get_fn: Callable,
    memory_create_fn: Callable,
    llm_chat_fn: Callable | None = None,
) -> dict:
    """把知识库文档导入为记忆条目。

    knowledge_get_fn: async (doc_id) -> dict with title, content
    memory_create_fn: async (tenant_id, layer, content, tags, ...) -> dict
    """
    imported = 0
    failed = 0

    for doc_id in document_ids:
        try:
            doc = await knowledge_get_fn(doc_id)
            if not doc:
                failed += 1
                continue

            title = doc.get("title", f"文档#{doc_id}")
            content = doc.get("content", "")[:2000]

            # LLM 摘要
            summary = title
            tags = ["imported_from_kb"]
            has_redlines = False

            if llm_chat_fn and content:
                summary_result = await summarize_document(title, content, llm_chat_fn)
                summary = summary_result.get("summary", title)
                tags = tags + summary_result.get("suggested_tags", [])
                has_redlines = summary_result.get("has_redlines", False)

            # 如果有红线，强制设为 enterprise 层
            layer = target_layer
            if has_redlines:
                layer = "enterprise"
                tags.append("redline")

            await memory_create_fn(
                tenant_id=tenant_id,
                layer=layer,
                content=f"[知识库导入] {title}\n\n{summary}",
                tags=tags + [f"kb_doc:{doc_id}"],
                source_type="import",
                department_id=department_id,
                position_id=position_id,
            )
            imported += 1
        except Exception as e:
            logger.warning("import doc %s failed: %s", doc_id, e)
            failed += 1

    return {"imported": imported, "failed": failed}


__all__ = ["archive_memories_to_knowledge", "import_knowledge_to_memory", "unified_search"]
