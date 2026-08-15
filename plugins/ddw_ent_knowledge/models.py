"""ORM 模型：Document / DocumentChunk / SearchLog。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import BigInt, TenantMixin, TimestampMixin
from core.database.session import Base


class Document(Base, TenantMixin, TimestampMixin):
    __tablename__ = "kb_documents"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    doc_uuid: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="ready", nullable=False)
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class DocumentChunk(Base, TenantMixin):
    __tablename__ = "kb_document_chunks"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(BigInt, nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class SearchLog(Base, TenantMixin):
    __tablename__ = "kb_search_logs"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    took_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
