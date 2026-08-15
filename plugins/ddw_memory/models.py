"""ddw_memory ORM + Pydantic models — 四层持久化记忆引擎。

数据库无关铁律：JSON 统一用 JSONEncodedText（存 TEXT），
时间戳统一用 UTCDateTime，索引字符串用 String。
"""
from __future__ import annotations

# Python 3.9: Optional 而非 PEP604 联合类型（SQLAlchemy 注解运行时求值）
import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import BigInt, TenantMixin, TimestampMixin
from core.database.session import Base
from core.database.types import JSONEncodedText


def _uuid() -> str:
    return str(uuid.uuid4())


# ──────────────────────────────────────────────────────────────
# Pydantic schemas (API 层)
# ──────────────────────────────────────────────────────────────


class MemoryLayer(str, Enum):
    PERSONAL = "personal"
    POSITION = "position"
    DEPARTMENT = "department"
    ENTERPRISE = "enterprise"


class MemoryEntryOut(BaseModel):
    id: int
    memory_uuid: str
    layer: MemoryLayer
    content: str
    summary: str | None = None
    creator_id: int
    department_id: int | None = None
    position_id: int | None = None
    tags: list[str] = []
    source_type: str = "manual"
    source_session_id: str | None = None
    expires_at: datetime | None = None
    is_deleted: bool = False
    created_at: datetime
    updated_at: datetime


class MemoryCreateReq(BaseModel):
    layer: MemoryLayer
    content: str
    creator_id: int
    department_id: int | None = None
    position_id: int | None = None
    tags: list[str] = []
    source_type: str = "manual"
    expires_at: datetime | None = None


class MemoryUpdateReq(BaseModel):
    content: str | None = None
    summary: str | None = None
    tags: list[str] | None = None
    expires_at: datetime | None = None


class MemorySearchReq(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    layers: list[MemoryLayer] = []
    department_id: int | None = None
    position_id: int | None = None
    top_k: int = Field(default=10, ge=1, le=50)
    search_mode: str = Field(default="hybrid", pattern=r"^(keyword|vector|hybrid)$")


class MemorySearchHit(BaseModel):
    entry: MemoryEntryOut
    score: float
    match_type: str
    layer_weight: float = 1.0


class MemorySearchResponse(BaseModel):
    hits: list[MemorySearchHit]
    total: int
    took_ms: int


class PositionSOPTemplateOut(BaseModel):
    id: int
    template_uuid: str
    position_name: str
    position_id: int | None = None
    sop_steps: list[str]
    knowledge_doc_ids: list[str] = []
    applicable_departments: list[int] = []
    version: int = 1
    created_at: datetime


class PositionSOPTemplateCreateReq(BaseModel):
    position_name: str
    position_id: int | None = None
    sop_steps: list[str]
    knowledge_doc_ids: list[str] = []
    applicable_departments: list[int] = []


class PositionSOPTemplateUpdateReq(BaseModel):
    sop_steps: list[str] | None = None
    knowledge_doc_ids: list[str] | None = None
    applicable_departments: list[int] | None = None


class PositionKnowledgeQueryReq(BaseModel):
    position_id: int
    question: str = Field(..., min_length=1, max_length=2000)


class PositionKnowledgeQueryResp(BaseModel):
    sop_steps: list[str]
    position_memories: list[MemoryEntryOut]
    enterprise_redlines: list[MemoryEntryOut]
    ai_answer: str
    sources: list[str]


class SessionSummaryCaptureReq(BaseModel):
    session_id: str
    user_id: int
    messages: list[dict]


class AutoCaptureConfigOut(BaseModel):
    enabled: bool = True
    capture_after_turns: int = 5
    auto_archive_to_department: bool = False
    exclude_patterns: list[str] = []


class AutoCaptureConfigUpdateReq(BaseModel):
    enabled: bool | None = None
    capture_after_turns: int | None = Field(None, ge=2, le=20)
    auto_archive_to_department: bool | None = None
    exclude_patterns: list[str] | None = None


class MemoryMigrationReq(BaseModel):
    source_user_id: int
    target_user_id: int
    scope: str = Field("personal", pattern=r"^(personal|position|all)$")


class LayerConfigReq(BaseModel):
    layers: list[MemoryLayer]


class MemoryStatsOut(BaseModel):
    total_entries: int
    by_layer: dict[str, int]
    auto_captured_today: int
    distill_count: int
    sop_template_count: int


# ──────────────────────────────────────────────────────────────
# SQLAlchemy ORM 模型
# ──────────────────────────────────────────────────────────────


class MemoryORM(Base, TenantMixin, TimestampMixin):
    """记忆条目持久化表。"""
    __tablename__ = "ddw_memories"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    memory_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid, index=True)
    layer: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    creator_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    department_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    position_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    tags: Mapped[list | None] = mapped_column(JSONEncodedText, nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), default="manual")
    source_session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_mem_tenant_layer", "tenant_id", "layer"),
        Index("idx_mem_tenant_dept", "tenant_id", "department_id"),
        Index("idx_mem_creator", "creator_id"),
    )


class PositionSOPTemplateORM(Base, TenantMixin, TimestampMixin):
    """岗位 SOP 模板。"""
    __tablename__ = "ddw_memory_sop_templates"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    template_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid, index=True)
    position_name: Mapped[str] = mapped_column(String(128), nullable=False)
    position_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sop_steps: Mapped[list] = mapped_column(JSONEncodedText, nullable=False)
    knowledge_doc_ids: Mapped[list | None] = mapped_column(JSONEncodedText, nullable=True)
    applicable_departments: Mapped[list | None] = mapped_column(JSONEncodedText, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (
        Index("idx_sop_tenant_pos", "tenant_id", "position_id"),
    )


class AutoCaptureConfigORM(Base, TenantMixin):
    """自动捕获配置（每租户一条）。"""
    __tablename__ = "ddw_memory_capture_config"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    capture_after_turns: Mapped[int] = mapped_column(Integer, default=5)
    auto_archive_to_department: Mapped[bool] = mapped_column(Boolean, default=False)
    exclude_patterns: Mapped[list | None] = mapped_column(JSONEncodedText, nullable=True)


class AutoCapturePendingORM(Base, TenantMixin, TimestampMixin):
    """待审核的自动捕获记忆。"""
    __tablename__ = "ddw_memory_capture_pending"

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    capture_uuid: Mapped[str] = mapped_column(String(36), unique=True, default=_uuid, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    knowledge_points: Mapped[list | None] = mapped_column(JSONEncodedText, nullable=True)
    suggested_layer: Mapped[str] = mapped_column(String(20), default="personal")
    suggested_tags: Mapped[list | None] = mapped_column(JSONEncodedText, nullable=True)
    confidence: Mapped[float] = mapped_column(default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


__all__ = [
    "AutoCaptureConfigORM",
    "AutoCaptureConfigOut",
    "AutoCaptureConfigUpdateReq",
    "AutoCapturePendingORM",
    "LayerConfigReq",
    "MemoryCreateReq",
    "MemoryEntryOut",
    "MemoryLayer",
    "MemoryMigrationReq",
    "MemoryORM",
    "MemorySearchHit",
    "MemorySearchReq",
    "MemorySearchResponse",
    "MemoryStatsOut",
    "MemoryUpdateReq",
    "PositionKnowledgeQueryReq",
    "PositionKnowledgeQueryResp",
    "PositionSOPTemplateCreateReq",
    "PositionSOPTemplateORM",
    "PositionSOPTemplateOut",
    "PositionSOPTemplateUpdateReq",
    "SessionSummaryCaptureReq",
]
