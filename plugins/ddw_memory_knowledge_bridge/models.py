"""Pydantic schemas for the bridge plugin (no ORM — bridge has no own tables)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class UnifiedSearchReq(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    search_memory: bool = True
    search_knowledge: bool = True
    memory_layers: list[str] = []
    top_k: int = Field(default=10, ge=1, le=50)
    user_id: int = 1
    department_id: int | None = None
    position_id: int | None = None


class UnifiedSearchHit(BaseModel):
    source: str  # "memory" | "knowledge"
    source_id: str
    content: str
    summary: str | None = None
    score: float
    layer: str | None = None
    doc_title: str | None = None
    created_at: datetime | None = None


class UnifiedSearchResponse(BaseModel):
    hits: list[UnifiedSearchHit]
    total: int
    memory_count: int
    knowledge_count: int
    took_ms: int


class MemoryToKnowledgeReq(BaseModel):
    memory_ids: list[int]
    target_bucket: str | None = None
    auto_classify: bool = True


class KnowledgeToMemoryReq(BaseModel):
    document_ids: list[str]
    target_layer: str = "department"
    department_id: int | None = None
    position_id: int | None = None


class SyncStatusOut(BaseModel):
    last_memory_to_knowledge_sync: datetime | None = None
    last_knowledge_to_memory_sync: datetime | None = None
    pending_memory_archives: int = 0
    pending_knowledge_imports: int = 0
    total_synced: int = 0


class ClassifyResult(BaseModel):
    suggested_bucket: str
    suggested_tags: list[str]
    confidence: float
    reasoning: str


__all__ = [
    "ClassifyResult",
    "KnowledgeToMemoryReq",
    "MemoryToKnowledgeReq",
    "SyncStatusOut",
    "UnifiedSearchHit",
    "UnifiedSearchReq",
    "UnifiedSearchResponse",
]
