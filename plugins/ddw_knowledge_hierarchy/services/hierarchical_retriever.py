"""层级检索器：三阶段检索引擎。

Phase 1 (导航): LLM 扫描文档树摘要 → 判断信息在哪些章节
Phase 2 (精确检索): 在选定章节内做向量搜索
Phase 3 (回答): LLM 结合检索结果生成结构化回答

支持三种模式：
- hierarchical: 完整三阶段（最准确）
- flat: 跳过 Phase 1，直接向量搜索（传统 RAG）
- hybrid: Phase 1 + Phase 2 并行，结果融合
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Document, SearchQueryLog, TreeNode
from .embedding_service import EmbeddingService, get_default_embedding
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


@dataclass
class NavigationNode:
    """Phase 1 导航结果。"""
    tree_node_id: str
    title: str
    node_type: str
    node_number: str = ""
    summary: str = ""
    confidence: float = 0.0
    reasoning: str = ""


@dataclass
class RetrievalChunk:
    """Phase 2 检索结果。"""
    chunk_id: str
    content: str
    score: float
    tree_node_path: str = ""
    page_number: Optional[int] = None
    section_title: str = ""


@dataclass
class HierarchicalSearchResult:
    """完整层级检索结果。"""
    query: str
    search_mode: str
    total_duration_ms: int = 0

    # Phase 1
    navigation_nodes: List[NavigationNode] = field(default_factory=list)
    navigation_duration_ms: int = 0
    navigation_tokens: int = 0

    # Phase 2
    retrieval_chunks: List[RetrievalChunk] = field(default_factory=list)
    retrieval_duration_ms: int = 0

    # Phase 3
    answer: str = ""
    cited_sources: List[Dict[str, Any]] = field(default_factory=list)
    answer_duration_ms: int = 0
    answer_tokens: int = 0

    log_id: str = ""


class HierarchicalRetriever:
    """层级检索器。"""

    def __init__(
        self,
        db_session: AsyncSession,
        vector_store: VectorStore,
        embedding_service: Optional[EmbeddingService] = None,
        llm_chat_fn=None,  # async (prompt, system) -> str
    ) -> None:
        self.db = db_session
        self.vs = vector_store
        self.emb = embedding_service or get_default_embedding()
        self.llm_chat = llm_chat_fn

    async def search(
        self,
        query: str,
        tenant_id: int = 0,
        knowledge_buckets: Optional[List[str]] = None,
        document_ids: Optional[List[str]] = None,
        max_navigation_nodes: int = 5,
        max_retrieval_chunks: int = 10,
        search_mode: str = "hybrid",
    ) -> HierarchicalSearchResult:
        """执行层级检索。"""
        start = time.monotonic()
        result = HierarchicalSearchResult(query=query, search_mode=search_mode)

        if search_mode == "flat":
            # 直接向量搜索
            result.retrieval_chunks = await self._flat_search(
                query, tenant_id, max_retrieval_chunks, document_ids
            )
            result.retrieval_duration_ms = int((time.monotonic() - start) * 1000)
        elif search_mode == "hierarchical":
            # Phase 1 → Phase 2 → Phase 3
            nav_start = time.monotonic()
            result.navigation_nodes = await self._phase1_navigate(
                query, tenant_id, max_navigation_nodes, document_ids
            )
            result.navigation_duration_ms = int((time.monotonic() - nav_start) * 1000)

            ret_start = time.monotonic()
            # 从导航结果中提取文档 ID
            nav_doc_ids = list(set(n.tree_node_id for n in result.navigation_nodes))
            result.retrieval_chunks = await self._phase2_retrieve(
                query, tenant_id, max_retrieval_chunks,
                document_ids or nav_doc_ids,
            )
            result.retrieval_duration_ms = int((time.monotonic() - ret_start) * 1000)

            # Phase 3: 生成回答
            if self.llm_chat and result.retrieval_chunks:
                ans_start = time.monotonic()
                answer_data = await self._phase3_answer(query, result.retrieval_chunks)
                result.answer = answer_data.get("answer", "")
                result.cited_sources = answer_data.get("sources", [])
                result.answer_duration_ms = int((time.monotonic() - ans_start) * 1000)
        elif search_mode == "hybrid":
            # 并行执行 Phase 1 和直接向量搜索，融合结果
            import asyncio
            nav_task = self._phase1_navigate(
                query, tenant_id, max_navigation_nodes, document_ids
            )
            flat_task = self._flat_search(
                query, tenant_id, max_retrieval_chunks, document_ids
            )
            nav_start = time.monotonic()
            nav_results, flat_results = await asyncio.gather(nav_task, flat_task)
            result.navigation_nodes = nav_results
            result.navigation_duration_ms = int((time.monotonic() - nav_start) * 1000)

            # 融合：去重 + 按 score 排序
            seen_chunks = set()
            merged: List[RetrievalChunk] = []
            for chunk in flat_results:
                if chunk.chunk_id not in seen_chunks:
                    seen_chunks.add(chunk.chunk_id)
                    merged.append(chunk)
            merged.sort(key=lambda x: x.score, reverse=True)
            result.retrieval_chunks = merged[:max_retrieval_chunks]
            result.retrieval_duration_ms = result.navigation_duration_ms

        result.total_duration_ms = int((time.monotonic() - start) * 1000)

        # 记录日志
        try:
            log = SearchQueryLog(
                query=query,
                navigation_result={"nodes": [
                    {"title": n.title, "confidence": n.confidence, "reasoning": n.reasoning}
                    for n in result.navigation_nodes
                ]},
                retrieval_result={"chunks": [
                    {"chunk_id": c.chunk_id, "score": c.score, "content_preview": c.content[:100]}
                    for c in result.retrieval_chunks
                ]},
                final_answer=result.answer,
                sources_cited=result.cited_sources,
                navigation_duration_ms=result.navigation_duration_ms,
                retrieval_duration_ms=result.retrieval_duration_ms,
                answer_duration_ms=result.answer_duration_ms,
            )
            self.db.add(log)
            await self.db.flush()
            result.log_id = log.id
        except Exception as e:
            logger.warning("Failed to log search query: %s", e)

        return result

    # ─── Phase 1: LLM 导航 ───

    async def _phase1_navigate(
        self, query: str, tenant_id: int, max_nodes: int,
        document_ids: Optional[List[str]] = None,
    ) -> List[NavigationNode]:
        """Phase 1: LLM 扫描文档树摘要，判断信息位置。"""
        if not self.llm_chat:
            return []

        # 获取文档树摘要
        stmt = select(TreeNode).where(TreeNode.summary.isnot(None))
        if document_ids:
            stmt = stmt.where(TreeNode.document_id.in_(document_ids))
        result = await self.db.execute(stmt)
        nodes = result.scalars().all()

        if not nodes:
            return []

        # 构建摘要上下文
        summaries = []
        for node in nodes:
            doc_stmt = select(Document).where(Document.id == node.document_id)
            doc_result = await self.db.execute(doc_stmt)
            doc = doc_result.scalar_one_or_none()
            doc_title = doc.title if doc else "未知文档"
            summaries.append(
                f"[{node.id}] 《{doc_title}》 > {node.title or node.node_type} "
                f"({node.node_number or ''}): {node.summary or '无摘要'}"
            )

        prompt = f"""你是文档导航助手。以下是企业知识库中各文档章节的摘要。

用户问题：{query}

文档章节摘要：
{chr(10).join(summaries[:200])}

请判断哪些章节最可能包含回答该问题的信息。返回 JSON 数组，每个元素：
{{"tree_node_id": "...", "confidence": 0.0-1.0, "reasoning": "判断理由"}}

最多返回 {max_nodes} 个最相关的章节。只返回 JSON 数组，不要其他内容。"""

        try:
            response = await self.llm_chat(prompt, "你是文档导航助手，返回纯 JSON。")
            # 解析 LLM 返回的 JSON
            response = response.strip()
            if response.startswith("```"):
                response = response.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            nav_data = json.loads(response)
            if not isinstance(nav_data, list):
                nav_data = [nav_data]

            nodes_map = {n.id: n for n in nodes}
            nav_nodes: List[NavigationNode] = []
            for item in nav_data[:max_nodes]:
                nid = item.get("tree_node_id", "")
                node = nodes_map.get(nid)
                if node:
                    nav_nodes.append(NavigationNode(
                        tree_node_id=nid,
                        title=node.title or node.node_type,
                        node_type=node.node_type,
                        node_number=node.node_number or "",
                        summary=node.summary or "",
                        confidence=float(item.get("confidence", 0.5)),
                        reasoning=item.get("reasoning", ""),
                    ))
            return nav_nodes
        except Exception as e:
            logger.warning("Phase 1 navigation failed: %s", e)
            return []

    # ─── Phase 2: 向量检索 ───

    async def _phase2_retrieve(
        self, query: str, tenant_id: int, top_k: int,
        filter_ids: Optional[List[str]] = None,
    ) -> List[RetrievalChunk]:
        """Phase 2: 在选定范围内做向量搜索。"""
        query_emb = await self.emb.embed(query)
        hits = self.vs.search(
            tenant_id=tenant_id,
            query_embedding=query_emb,
            top_k=top_k,
            doc_ids=filter_ids if filter_ids else None,
        )

        chunks: List[RetrievalChunk] = []
        for hit in hits:
            chunks.append(RetrievalChunk(
                chunk_id=hit["chunk_id"],
                content=hit["content"],
                score=hit["score"],
                section_title=hit.get("metadata", {}).get("section_title", ""),
                page_number=hit.get("metadata", {}).get("page_number"),
            ))
        return chunks

    # ─── Phase 3: LLM 回答 ───

    async def _phase3_answer(
        self, query: str, chunks: List[RetrievalChunk],
    ) -> Dict[str, Any]:
        """Phase 3: LLM 结合检索结果生成结构化回答。"""
        if not self.llm_chat:
            return {"answer": "", "sources": []}

        context_parts = []
        for i, chunk in enumerate(chunks[:10], 1):
            source_info = f"[来源{i}]"
            if chunk.section_title:
                source_info += f" {chunk.section_title}"
            if chunk.page_number:
                source_info += f" (第{chunk.page_number}页)"
            context_parts.append(f"{source_info}\n{chunk.content}")

        prompt = f"""你是企业知识库问答助手。基于以下检索到的知识片段回答用户问题。

用户问题：{query}

检索到的知识片段：
{chr(10).join(context_parts)}

要求：
1. 基于检索内容回答，不要编造信息
2. 引用来源时标注 [来源N]
3. 如果检索内容不足以回答，明确说明

回答："""

        try:
            answer = await self.llm_chat(prompt, "你是企业知识库问答助手，基于检索内容准确回答。")
            # 提取引用来源
            sources = []
            for i, chunk in enumerate(chunks[:10], 1):
                if f"[来源{i}]" in answer:
                    sources.append({
                        "chunk_id": chunk.chunk_id,
                        "section_title": chunk.section_title,
                        "page_number": chunk.page_number,
                        "score": chunk.score,
                    })
            return {"answer": answer, "sources": sources}
        except Exception as e:
            logger.warning("Phase 3 answer failed: %s", e)
            return {"answer": "", "sources": []}

    # ─── Flat 搜索 ───

    async def _flat_search(
        self, query: str, tenant_id: int, top_k: int,
        doc_ids: Optional[List[str]] = None,
    ) -> List[RetrievalChunk]:
        """传统 flat chunking 搜索（兼容模式）。"""
        return await self._phase2_retrieve(query, tenant_id, top_k, doc_ids)
