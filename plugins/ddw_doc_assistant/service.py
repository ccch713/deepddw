"""Doc Assistant service — 上传解析 · 分块入库 · 混合检索 · RAG问答。

复用 ddw_knowledge_hierarchy 的:
  - document_parser.parse_document  (文本提取)
  - chunker.chunk_text              (分块)
  - embedding_service               (向量化)
  - vector_store.VectorStore        (向量存储)
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_knowledge_hierarchy.services.chunker import chunk_text
from plugins.ddw_knowledge_hierarchy.services.document_parser import parse_document
from plugins.ddw_knowledge_hierarchy.services.embedding_service import (
    get_default_embedding,
)
from plugins.ddw_knowledge_hierarchy.services.vector_store import VectorStore

from .models import DocMeta

logger = logging.getLogger(__name__)

# 类型别名
LLMChatFn = Callable[[str, str], Coroutine[Any, Any, Optional[str]]]


class DocAssistantService:
    """文档助手核心服务。"""

    def __init__(
        self,
        db: AsyncSession,
        vector_store: VectorStore,
        llm_chat_fn: Optional[LLMChatFn] = None,
    ) -> None:
        self._db = db
        self._vs = vector_store
        self._llm = llm_chat_fn
        self._embedding = get_default_embedding()

    # ─── 上传解析 + 分块入库 ───

    async def ingest_document(
        self,
        file_path: Path,
        *,
        title: Optional[str] = None,
        uploader: str = "",
        department: str = "",
        tenant_id: int = 0,
    ) -> DocMeta:
        """解析文档 → 分块 → embedding → 向量入库 → 写元数据。"""
        # 1. 解析
        parsed = parse_document(file_path)
        doc_title = title or parsed.title
        file_type = parsed.file_type
        file_size = file_path.stat().st_size if file_path.exists() else 0

        # 2. 分块
        chunks = chunk_text(parsed.raw_text)
        if not chunks:
            logger.warning("文档 %s 解析为空", doc_title)

        # 3. embedding
        contents = [c.content for c in chunks]
        embeddings = await self._embedding.embed_batch(contents) if contents else []

        # 4. 向量入库
        chunk_ids = [f"{_hash(doc_title)}_{c.chunk_index}" for c in chunks]
        if contents:
            self._vs.add(
                tenant_id=tenant_id,
                doc_id="",  # 先空，拿到 doc_id 后回填
                chunk_ids=chunk_ids,
                contents=contents,
                embeddings=embeddings,
            )

        # 5. 写 ORM 元数据
        doc = DocMeta(
            title=doc_title,
            file_type=file_type,
            file_size=file_size,
            uploader=uploader,
            department=department,
            chunk_count=len(chunks),
            vector_indexed=bool(contents),
        )
        self._db.add(doc)
        await self._db.flush()

        # 回填 doc_id 到向量库（先删再重写）
        if contents:
            self._vs.delete_by_doc(tenant_id, "")
            self._vs.add(
                tenant_id=tenant_id,
                doc_id=str(doc.id),
                chunk_ids=chunk_ids,
                contents=contents,
                embeddings=embeddings,
            )

        return doc

    # ─── 文档列表 ───

    async def list_documents(
        self,
        *,
        department: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> List[DocMeta]:
        """列出文档（按部门筛选，分页）。"""
        stmt = select(DocMeta).order_by(DocMeta.created_at.desc())
        if department:
            stmt = stmt.where(DocMeta.department == department)
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        rows = (await self._db.execute(stmt)).scalars().all()
        return list(rows)

    # ─── 删除文档 ───

    async def delete_document(self, doc_id: str, tenant_id: int = 0) -> bool:
        """删除文档 + 向量数据。返回是否成功。"""
        doc = (
            await self._db.execute(select(DocMeta).where(DocMeta.id == doc_id))
        ).scalar_one_or_none()
        if doc is None:
            return False
        self._vs.delete_by_doc(tenant_id, doc_id)
        await self._db.delete(doc)
        return True

    # ─── 获取文档 chunks ───

    async def get_document_chunks(self, doc_id: str) -> List[Dict[str, Any]]:
        """从向量库获取指定文档的所有 chunks。"""
        with self._vs._lock, self._vs._conn() as c:
            rows = c.execute(
                "SELECT * FROM kh_vector_chunks WHERE doc_id=? ORDER BY chunk_id",
                (doc_id,),
            ).fetchall()
        return [
            {
                "id": row["chunk_id"],
                "chunk_index": i,
                "content": row["content"],
                "token_count": len(row["content"]),
                "page_number": None,
            }
            for i, row in enumerate(rows)
        ]

    # ─── 混合检索 + RAG 问答 ───

    async def query(
        self,
        question: str,
        *,
        doc_ids: Optional[List[str]] = None,
        top_k: int = 5,
        tenant_id: int = 0,
    ) -> Dict[str, Any]:
        """关键词+向量混合检索，生成 RAG 回答。"""
        # 1. 向量检索
        embedding = await self._embedding.embed(question)
        vs_results = self._vs.search(
            tenant_id=tenant_id,
            query_embedding=embedding,
            top_k=top_k,
            doc_ids=doc_ids or None,
        )

        # 2. 关键词增强（简单 BM25 策略: 对命中关键词的 chunk 提权）
        for r in vs_results:
            kw_boost = sum(
                0.05 for kw in question if kw in r.get("content", "")
            )
            r["score"] = round(r["score"] + min(kw_boost, 0.15), 4)
        vs_results.sort(key=lambda x: x["score"], reverse=True)
        vs_results = vs_results[:top_k]

        # 3. 构造来源列表（带文档标题）
        sources: List[Dict[str, Any]] = []
        doc_id_set = set()
        for r in vs_results:
            doc = (
                await self._db.execute(
                    select(DocMeta).where(DocMeta.id == r["doc_id"])
                )
            ).scalar_one_or_none()
            sources.append({
                "chunk_id": r["chunk_id"],
                "doc_id": r["doc_id"],
                "doc_title": doc.title if doc else "",
                "content": r["content"],
                "score": r["score"],
                "chunk_index": r.get("metadata", {}).get("chunk_index", 0),
            })
            doc_id_set.add(r["doc_id"])

        # 4. LLM 生成回答
        answer_text = ""
        if sources:
            if self._llm:
                context = "\n\n".join(
                    f"[来源{i+1}] {s['content']}" for i, s in enumerate(sources)
                )
                prompt = (
                    f"根据以下参考资料回答用户问题。如果资料中没有相关信息，请说明。\n\n"
                    f"参考资料:\n{context}\n\n用户问题: {question}"
                )
                answer_text = await self._llm(prompt, "") or ""
            else:
                # 无 LLM 时返回 top chunk 作为摘录式回答
                answer_text = (
                    f"基于知识库检索，找到 {len(sources)} 条相关内容：\n\n"
                    + "\n\n".join(
                        f"[{s['doc_title']}] {s['content'][:200]}"
                        for s in sources[:3]
                    )
                )
        else:
            answer_text = "未在知识库中找到相关内容。"

        return {
            "answer": answer_text,
            "sources": sources,
            "doc_ids_queried": list(doc_id_set),
        }


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]
