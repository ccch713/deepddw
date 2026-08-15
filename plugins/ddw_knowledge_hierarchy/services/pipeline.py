"""文档摄入管线：文件 → 解析 → 树构建 → 分块 → embedding → 向量存储。

完整流程：
1. 解析文档（PDF/DOCX/MD/TXT/HTML/Excel）
2. 构建层级树（DocumentTreeNode）
3. 分块（DocumentChunk）
4. 生成 embedding
5. 存入向量库
6. 生成章节摘要（LLM，可选）
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Document, DocumentChunk, TreeNode
from .chunker import chunk_text
from .document_parser import ParsedDocument, ParsedSection, parse_document
from .embedding_service import EmbeddingService, get_default_embedding
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """文档摄入管线。"""

    def __init__(
        self,
        db_session: AsyncSession,
        vector_store: VectorStore,
        embedding_service: Optional[EmbeddingService] = None,
        llm_chat_fn=None,
    ) -> None:
        self.db = db_session
        self.vs = vector_store
        self.emb = embedding_service or get_default_embedding()
        self.llm_chat = llm_chat_fn

    async def ingest(
        self,
        file_path: Path,
        tenant_id: int = 0,
        knowledge_bucket: str = "default",
        access_level: str = "internal",
        tags: Optional[List[str]] = None,
    ) -> Document:
        """完整摄入一个文档。"""
        # 1. 解析
        logger.info("Parsing document: %s", file_path)
        parsed = parse_document(file_path)

        # 2. 检查是否已存在（基于 file_hash）
        existing = await self._find_by_hash(parsed.file_hash)
        if existing:
            logger.info("Document already indexed (hash match): %s", existing.id)
            return existing

        # 3. 创建 Document 记录
        doc = Document(
            title=parsed.title,
            file_path=str(file_path),
            file_type=parsed.file_type,
            file_hash=parsed.file_hash,
            file_size=parsed.file_size,
            knowledge_bucket=knowledge_bucket,
            access_level=access_level,
            tags=tags,
        )
        self.db.add(doc)
        await self.db.flush()

        # 4. 构建层级树
        logger.info("Building tree for document: %s", doc.id)
        root_node = TreeNode(
            document_id=doc.id,
            node_type="document_root",
            title=parsed.title,
            order_index=0,
        )
        self.db.add(root_node)
        await self.db.flush()

        await self._build_tree(doc.id, root_node.id, parsed.sections)

        # 5. 分块 + embedding + 存储
        logger.info("Chunking and embedding document: %s", doc.id)
        all_chunks = self._chunk_document(parsed, doc.id)
        if all_chunks:
            # 批量生成 embedding
            texts = [c["content"] for c in all_chunks]
            embeddings = await self.emb.embed_batch(texts)

            # 保存 chunk 到数据库
            chunk_ids: List[str] = []
            for chunk_data, emb in zip(all_chunks, embeddings):
                chunk = DocumentChunk(
                    document_id=doc.id,
                    content=chunk_data["content"],
                    chunk_index=chunk_data["index"],
                    token_count=chunk_data["token_count"],
                    page_number=chunk_data.get("page_number"),
                    embedding_json=str(emb),  # 简化存储
                )
                self.db.add(chunk)
                await self.db.flush()
                chunk_ids.append(chunk.id)

            # 存入向量库
            self.vs.add(
                tenant_id=tenant_id,
                doc_id=doc.id,
                chunk_ids=chunk_ids,
                contents=texts,
                embeddings=embeddings,
                metadatas=[{"section_title": c.get("section_title", "")} for c in all_chunks],
            )

        doc.vector_indexed = True
        doc.hierarchy_indexed = True
        await self.db.flush()

        logger.info("Ingestion complete: %s (%d chunks)", doc.id, len(all_chunks))
        return doc

    async def _find_by_hash(self, file_hash: str) -> Optional[Document]:
        stmt = select(Document).where(Document.file_hash == file_hash)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _build_tree(
        self, doc_id: str, parent_id: str, sections: List[ParsedSection],
    ) -> None:
        """递归构建文档树。"""
        for i, sec in enumerate(sections):
            node = TreeNode(
                document_id=doc_id,
                parent_id=parent_id,
                node_type=self._level_to_type(sec.level),
                title=sec.title,
                node_number=sec.number,
                order_index=i,
            )
            self.db.add(node)
            await self.db.flush()

            # 递归子节点
            if sec.children:
                await self._build_tree(doc_id, node.id, sec.children)

    def _chunk_document(self, parsed: ParsedDocument, doc_id: str) -> List[Dict[str, Any]]:
        """将文档分割为 chunk。"""
        all_chunks: List[Dict[str, Any]] = []
        idx = 0

        # 从章节分块
        for sec in parsed.sections:
            path = self._section_path(sec)
            if sec.content:
                chunks = chunk_text(
                    sec.content, section_title=sec.title, section_path=path,
                )
                for c in chunks:
                    all_chunks.append({
                        "content": c.content,
                        "index": idx,
                        "token_count": c.token_count,
                        "section_title": sec.title,
                        "section_path": path,
                        "page_number": c.page_number,
                    })
                    idx += 1

            # 递归子节点
            for child in sec.children:
                child_chunks = self._chunk_section(child, idx, path)
                all_chunks.extend(child_chunks)
                idx += len(child_chunks)

        # 如果没有章节结构，用全文分块
        if not all_chunks and parsed.raw_text:
            chunks = chunk_text(parsed.raw_text)
            for c in chunks:
                all_chunks.append({
                    "content": c.content,
                    "index": idx,
                    "token_count": c.token_count,
                    "section_title": "",
                    "section_path": "",
                })
                idx += 1

        return all_chunks

    def _chunk_section(
        self, sec: ParsedSection, start_idx: int, parent_path: str,
    ) -> List[Dict[str, Any]]:
        """递归分块章节。"""
        path = f"{parent_path} > {sec.title}" if parent_path else sec.title
        result: List[Dict[str, Any]] = []
        idx = start_idx

        if sec.content:
            chunks = chunk_text(sec.content, section_title=sec.title, section_path=path)
            for c in chunks:
                result.append({
                    "content": c.content,
                    "index": idx,
                    "token_count": c.token_count,
                    "section_title": sec.title,
                    "section_path": path,
                    "page_number": c.page_number,
                })
                idx += 1

        for child in sec.children:
            child_chunks = self._chunk_section(child, idx, path)
            result.extend(child_chunks)
            idx += len(child_chunks)

        return result

    @staticmethod
    def _level_to_type(level: int) -> str:
        mapping = {1: "chapter", 2: "section", 3: "subsection", 4: "paragraph"}
        return mapping.get(level, "paragraph")

    @staticmethod
    def _section_path(sec: ParsedSection) -> str:
        return sec.title
