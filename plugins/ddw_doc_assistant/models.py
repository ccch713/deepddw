"""SQLAlchemy ORM + Pydantic schemas for Doc Assistant plugin."""
from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field
from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    __allow_unmapped__ = True


def _uuid() -> str:
    return str(uuid.uuid4())


# ─── ORM: 文档元数据表 ───

class DocMeta(Base):
    """文档元数据（独立表，前缀 da_）。"""
    __tablename__ = "da_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)  # pdf|docx|md|txt
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploader: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, index=True)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vector_indexed: Mapped[bool] = mapped_column(default=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_da_doc_dept", "department"),
    )


# ─── Pydantic: API 请求/响应 ───

class DocQueryRequest(BaseModel):
    """文档问答请求。"""
    question: str = Field(..., min_length=1, max_length=4000, description="用户问题")
    doc_ids: List[str] = Field(default=[], description="限定文档范围（空=全部）")
    top_k: int = Field(default=5, ge=1, le=50, description="返回 chunk 数量")


class SourceChunk(BaseModel):
    """引用来源。"""
    chunk_id: str
    doc_id: str
    doc_title: str = ""
    content: str
    score: float
    chunk_index: int = 0


class DocAnswer(BaseModel):
    """文档问答回答。"""
    answer: str
    sources: List[SourceChunk] = []
    doc_ids_queried: List[str] = []


class DocSchema(BaseModel):
    """文档列表/详情响应。"""
    id: str
    title: str
    file_type: str
    file_size: int
    uploader: str = ""
    department: str = ""
    chunk_count: int = 0
    vector_indexed: bool = False
    created_at: str = ""


class ChunkSchema(BaseModel):
    """单个 chunk。"""
    id: str
    chunk_index: int
    content: str
    token_count: int = 0
    page_number: Optional[int] = None


class UploadResponse(BaseModel):
    """上传响应。"""
    id: str
    title: str
    file_type: str
    file_size: int
    chunk_count: int
    vector_indexed: bool
    message: str = "ok"
