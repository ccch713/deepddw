"""文档入库服务：upload → parse → chunk → embed → write。"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_ent_knowledge.core.chunker import chunk_text
from plugins.ddw_ent_knowledge.core.document_parser import (
    SUPPORTED_EXTS,
    parse_bytes,
    parse_file,
)
from plugins.ddw_ent_knowledge.core.embedding import EmbeddingService
from plugins.ddw_ent_knowledge.core.vector_store import VectorStore
from plugins.ddw_ent_knowledge.models import Document, DocumentChunk

logger = logging.getLogger(__name__)


class IngestService:
    """文档入库：解析 → 分块 → embedding → 写入 ORM + 向量库。"""

    def __init__(
        self,
        embedding: EmbeddingService,
        vector_store: VectorStore,
        data_dir: str = "./data/kb",
    ) -> None:
        self.embedding = embedding
        self.vector_store = vector_store
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def ingest_upload(
        self,
        session: AsyncSession,
        tenant_id: int,
        filename: str,
        file_data: bytes,
    ) -> Dict[str, Any]:
        """从上传字节流入库。"""
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTS:
            return {"error": f"unsupported file type: {ext}", "status": "failed"}

        text, err = parse_bytes(filename, file_data)
        if err or not text.strip():
            doc_uuid = str(uuid.uuid4())
            doc = Document(
                tenant_id=tenant_id,
                doc_uuid=doc_uuid,
                file_name=filename,
                file_type=ext.lstrip("."),
                chunk_count=0,
                status="failed",
                error_msg=err or "empty content",
            )
            session.add(doc)
            await session.flush()
            return {"doc_id": doc.id, "doc_uuid": doc_uuid, "status": "failed", "error": err}

        return await self._ingest_text(session, tenant_id, filename, ext, text)

    async def ingest_file(
        self,
        session: AsyncSession,
        tenant_id: int,
        file_path: Path,
    ) -> Dict[str, Any]:
        """从文件路径入库。"""
        text, err = parse_file(file_path)
        if err or not text.strip():
            doc_uuid = str(uuid.uuid4())
            doc = Document(
                tenant_id=tenant_id,
                doc_uuid=doc_uuid,
                file_name=file_path.name,
                file_type=file_path.suffix.lstrip("."),
                chunk_count=0,
                status="failed",
                error_msg=err or "empty content",
            )
            session.add(doc)
            await session.flush()
            return {"doc_id": doc.id, "doc_uuid": doc_uuid, "status": "failed", "error": err}

        return await self._ingest_text(session, tenant_id, file_path.name, file_path.suffix, text)

    async def _ingest_text(
        self,
        session: AsyncSession,
        tenant_id: int,
        filename: str,
        ext: str,
        text: str,
    ) -> Dict[str, Any]:
        doc_uuid = str(uuid.uuid4())

        # 分块
        chunks = chunk_text(text)
        if not chunks:
            doc = Document(
                tenant_id=tenant_id,
                doc_uuid=doc_uuid,
                file_name=filename,
                file_type=ext.lstrip("."),
                chunk_count=0,
                status="failed",
                error_msg="no chunks produced (content too short)",
            )
            session.add(doc)
            await session.flush()
            return {"doc_id": doc.id, "doc_uuid": doc_uuid, "status": "failed", "error": "no chunks"}

        # Embedding
        self.embedding.fit_idf(chunks)
        embeddings = await self.embedding.embed_batch(chunks)

        # 写入向量库
        chunk_ids = self.vector_store.add(
            tenant_id=tenant_id,
            doc_id=doc_uuid,
            contents=chunks,
            embeddings=embeddings,
        )

        # 写入 ORM
        doc = Document(
            tenant_id=tenant_id,
            doc_uuid=doc_uuid,
            file_name=filename,
            file_type=ext.lstrip("."),
            chunk_count=len(chunks),
            status="ready",
        )
        session.add(doc)
        await session.flush()

        for i, (chunk_text_val, cid) in enumerate(zip(chunks, chunk_ids)):
            dc = DocumentChunk(
                tenant_id=tenant_id,
                doc_id=doc.id,
                chunk_index=i,
                content=chunk_text_val,
                embedding_json=json.dumps(embeddings[i], ensure_ascii=False),
                metadata_json=json.dumps({"vector_id": cid}, ensure_ascii=False),
            )
            session.add(dc)

        await session.flush()

        return {
            "doc_id": doc.id,
            "doc_uuid": doc_uuid,
            "file_name": filename,
            "chunk_count": len(chunks),
            "status": "ready",
        }

    async def delete_document(
        self,
        session: AsyncSession,
        tenant_id: int,
        doc_id: int,
    ) -> bool:
        """删除文档及其 chunks。"""
        result = await session.execute(
            select(Document).where(Document.tenant_id == tenant_id, Document.id == doc_id)
        )
        doc = result.scalar_one_or_none()
        if not doc:
            return False

        # 删除向量库中的 chunks
        self.vector_store.delete_by_doc(tenant_id, doc.doc_uuid)

        # 删除 ORM chunks
        await session.execute(
            select(DocumentChunk).where(DocumentChunk.tenant_id == tenant_id, DocumentChunk.doc_id == doc_id)
        )
        # Use raw delete
        from sqlalchemy import delete as sqla_delete
        await session.execute(
            sqla_delete(DocumentChunk).where(DocumentChunk.tenant_id == tenant_id, DocumentChunk.doc_id == doc_id)
        )
        await session.delete(doc)
        await session.flush()
        return True


__all__ = ["IngestService"]
