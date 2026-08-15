"""SQLAlchemy ORM models for Knowledge Hierarchy plugin.

Based on PRD_ddw-knowledge-hierarchy_v1.0.0 data model.
Uses SQLAlchemy 2.0 Mapped[] syntax.
"""
from __future__ import annotations

import datetime
import uuid
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    __allow_unmapped__ = True


def _uuid() -> str:
    return str(uuid.uuid4())


# ─── Document (文档主表) ───

class Document(Base):
    """知识库文档主表。"""
    __tablename__ = "kh_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    file_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # pdf|docx|md|txt|html|xlsx
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)  # SHA256
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 元数据
    author: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    tags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # 索引状态
    hierarchy_indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    vector_indexed: Mapped[bool] = mapped_column(Boolean, default=False)

    # 知识桶（分类）
    knowledge_bucket: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )

    # 权限
    access_level: Mapped[str] = mapped_column(
        String(32), default="internal"
    )  # public|internal|restricted

    # 时间戳
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # 关系
    tree_nodes: Mapped[List["TreeNode"]] = relationship(
        "TreeNode", back_populates="document", cascade="all, delete-orphan"
    )
    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_kh_doc_bucket", "knowledge_bucket"),
        Index("idx_kh_doc_hash", "file_hash"),
    )


# ─── TreeNode (文档树节点) ───

class TreeNode(Base):
    """自引用树结构：document > chapter > section > page > paragraph。"""
    __tablename__ = "kh_tree_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kh_documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("kh_tree_nodes.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )

    # 节点信息
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # node_type: document_root | part | chapter | section | subsection | page | paragraph | table | figure

    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    node_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # "3.2.1"

    # LLM 生成的摘要（用于层级导航）
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 排序
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 内容范围（指向 chunk 的范围）
    content_start_chunk_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("kh_chunks.id"), nullable=True
    )
    content_end_chunk_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("kh_chunks.id"), nullable=True
    )

    # 元数据
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # 关系
    document: Mapped["Document"] = relationship("Document", back_populates="tree_nodes")
    parent: Mapped[Optional["TreeNode"]] = relationship(
        "TreeNode", remote_side="TreeNode.id", backref="children"
    )

    __table_args__ = (
        Index("idx_kh_tree_doc_parent", "document_id", "parent_id"),
        Index("idx_kh_tree_doc_type", "document_id", "node_type"),
    )


# ─── DocumentChunk (文档片段) ───

class DocumentChunk(Base):
    """文档分块，含 embedding 向量。"""
    __tablename__ = "kh_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("kh_documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    tree_node_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("kh_tree_nodes.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # 内容
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Token 统计
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 向量（SQLite 用 JSON，PostgreSQL 用 pgvector）
    embedding_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 排序
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 元数据
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_table: Mapped[bool] = mapped_column(Boolean, default=False)
    is_figure: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    # 关系
    document: Mapped["Document"] = relationship("Document", back_populates="chunks")
    tree_node: Mapped[Optional["TreeNode"]] = relationship(
        "TreeNode", foreign_keys=[tree_node_id]
    )

    __table_args__ = (
        Index("idx_kh_chunk_doc_index", "document_id", "chunk_index"),
        Index("idx_kh_chunk_node", "tree_node_id"),
    )


# ─── SearchQueryLog (检索日志) ───

class SearchQueryLog(Base):
    """检索日志，用于调试和改进。"""
    __tablename__ = "kh_search_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    query: Mapped[str] = mapped_column(Text, nullable=False)

    # Phase 1 结果（LLM 导航）
    navigation_result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Phase 2 结果（向量检索）
    retrieval_result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # 最终回答
    final_answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sources_cited: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # 用户反馈
    user_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5
    user_feedback_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Token 消耗
    navigation_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    retrieval_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    answer_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 耗时
    navigation_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    retrieval_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    answer_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_kh_log_created", "created_at"),
    )


# ─── KnowledgeBucket (知识桶) ───

class KnowledgeBucket(Base):
    """知识桶（分类容器）。"""
    __tablename__ = "kh_buckets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    access_roles: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


# ─── DocumentTemplate (文档生成模板) ───

class DocumentTemplate(Base):
    """文档生成模板（8D/CAPA/质量报警/COA等）。"""
    __tablename__ = "kh_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    template_type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )  # 8d|capa|quality_alert|coa|fmea|spc|custom
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True
    )  # food|pharma|general
    content_template: Mapped[str] = mapped_column(Text, nullable=False)  # Jinja2 template
    metadata_schema: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


# ─── GeneratedDocument (已生成文档) ───

class GeneratedDocument(Base):
    """已生成的文档记录。"""
    __tablename__ = "kh_generated_docs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    template_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("kh_templates.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    knowledge_bucket: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, index=True
    )
    source_document_ids: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # 引用的知识库文档 ID 列表
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )


# ─── KnowledgeBase (知识库 — 公司/部门/员工三层权限) ───

class KnowledgeBase(Base):
    """知识库：支持 company / department / personal 三级可见范围。"""
    __tablename__ = "kh_knowledge_bases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    scope: Mapped[str] = mapped_column(String(20), default="company")  # company/department/personal
    scope_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    department_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False)
    doc_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[List["KBDocument"]] = relationship(
        "KBDocument", back_populates="knowledge_base", cascade="all, delete-orphan"
    )


# ─── KBDocument (知识库文档) ───

class KBDocument(Base):
    """知识库文档（归属于某个 KnowledgeBase）。"""
    __tablename__ = "kh_kb_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kb_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("kh_knowledge_bases.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), default="pdf")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="indexed")  # indexing/indexed/error
    uploaded_by: Mapped[int] = mapped_column(Integer, nullable=False)
    content_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    knowledge_base: Mapped["KnowledgeBase"] = relationship(
        "KnowledgeBase", back_populates="documents"
    )


# ─── KhDistillJob (蒸馏任务) ───

class KhDistillJob(Base):
    """方法论蒸馏任务。"""
    __tablename__ = "kh_distill_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    knowledge_base_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    # status: queued | extracting | verifying | constructing | completed | failed
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0-100
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    completed_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime, nullable=True
    )

    __table_args__ = (
        Index("idx_kh_distill_job_tenant", "tenant_id"),
        Index("idx_kh_distill_job_kb", "knowledge_base_id"),
    )


# ─── KhMethodologyUnit (方法论单元 = skill 卡片) ───

class KhMethodologyUnit(Base):
    """方法论单元（RIA++ 六段构造）。"""
    __tablename__ = "kh_methodology_units"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    distill_job_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    document_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    unit_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # unit_type: framework | principle | case | counter_example | glossary
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    trigger_words: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    r_section: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    i_section: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    a1_section: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    e_section: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    b_section: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    v1_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    v2_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    v3_passed: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="verified")
    # status: verified | rejected
    reject_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_chapter: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_kh_unit_job", "distill_job_id"),
        Index("idx_kh_unit_doc", "document_id"),
        Index("idx_kh_unit_tenant", "tenant_id"),
    )
