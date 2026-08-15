"""Pydantic 请求/响应模型。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: int
    doc_uuid: str
    file_name: str
    file_type: str
    chunk_count: int
    status: str
    created_at: Optional[str] = None


class DocumentListOut(BaseModel):
    items: List[DocumentOut]
    total: int


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class SearchHit(BaseModel):
    content: str
    score: float
    doc_id: str
    metadata: Dict[str, Any] = {}


class SearchResponse(BaseModel):
    hits: List[SearchHit]
    took_ms: int


class ChatRequest(BaseModel):
    query: str
    top_k: int = 5
