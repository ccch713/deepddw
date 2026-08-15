"""DDW 投标标书插件 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database.session import Base
from core.database.tenant_filter import TENANT_AWARE_ATTR

# 兼容 SQLite
BigInt = Integer()


class BidProject(Base):
    """投标项目主表。"""

    __tablename__ = "bid_projects"
    __table_args__ = {"extend_existing": True}
    __tenant_aware__ = True  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    project_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    client_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    bid_deadline: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    project_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    estimated_amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class BidDocument(Base):
    """标书文档。"""

    __tablename__ = "bid_documents"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bid_project_id: Mapped[int] = mapped_column(Integer, ForeignKey("bid_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 技术标/商务标/资格预审
    style: Mapped[str] = mapped_column(String(50), default="标准", nullable=False)  # 标准/保守/激进/创新型
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)  # draft/reviewed/approved
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class BidTemplate(Base):
    """标书模板。"""

    __tablename__ = "bid_templates"
    __table_args__ = {"extend_existing": True}
    __tenant_aware__ = True  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# 知识库 & 章节 & 进度（C+D+E+F 方案新增）
# ---------------------------------------------------------------------------


class KnowledgeDocument(Base):
    """租户的历史标书文档（学习用）。"""

    __tablename__ = "bid_kb_documents"
    __table_args__ = {"extend_existing": True}
    __tenant_aware__ = True  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # 内部唯一 ID
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    doc_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)  # 技术标/商务标/...
    project_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)  # 住宅/商业/...
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 抽取出的纯文本
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)  # pending/ready/failed
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class KnowledgeBootstrapRun(Base):
    """知识库学习运行记录。"""

    __tablename__ = "bid_kb_runs"
    __table_args__ = {"extend_existing": True}
    __tenant_aware__ = True  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    folder: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False, index=True)  # running/success/failed
    total_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_files: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    templates_extracted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class FactTemplate(Base):
    """从历史标书抽出的 FactSheet 模板（按 project_type 维度）。"""

    __tablename__ = "bid_fact_templates"
    __table_args__ = {"extend_existing": True}
    __tenant_aware__ = True  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    project_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    doc_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    section_structure: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON: 章节结构
    personnel_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON: 人员模板
    style_baseline: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class BidSection(Base):
    """标书章节记录（F 渐进式披露 + C 阶段 2 支撑）。"""

    __tablename__ = "bid_sections"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bid_document_id: Mapped[int] = mapped_column(Integer, ForeignKey("bid_documents.id", ondelete="CASCADE"), nullable=False, index=True)
    section_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3...
    section_title: Mapped[str] = mapped_column(String(200), nullable=False)
    section_role: Mapped[str] = mapped_column(String(80), default="", nullable=False)  # planner/writer/reviewer
    outline_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 大纲摘要
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 生成内容
    rag_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 检索到的相似案例
    fact_sheet_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 生成时的事实表快照
    is_locked: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0/1：是否被用户锁定
    review_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class AgentRun(Base):
    """多 agent 协作运行记录（E 方案）。"""

    __tablename__ = "bid_agent_runs"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    bid_project_id: Mapped[int] = mapped_column(Integer, ForeignKey("bid_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    bid_document_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("bid_documents.id", ondelete="SET NULL"), nullable=True)
    mode: Mapped[str] = mapped_column(String(20), default="full", nullable=False)  # full/auto/important
    agents_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON：每个 agent 的输入输出
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)  # running/success/failed
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


__all__ = [
    "TENANT_AWARE_ATTR",
    "AgentRun",
    "BidDocument",
    "BidProject",
    "BidSection",
    "BidTemplate",
    "FactTemplate",
    "KnowledgeBootstrapRun",
    "KnowledgeDocument",
]
