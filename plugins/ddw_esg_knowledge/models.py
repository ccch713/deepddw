"""SQLAlchemy ORM + Pydantic models for ESG Knowledge Base."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field
from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, relationship

# ---------------------------------------------------------------------------
# SQLAlchemy Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class Customer(Base):
    __tablename__ = "esg_knowledge_customers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(256), nullable=False)
    short_name = Column(String(128))
    stock_code = Column(String(16))
    industry = Column(String(128))
    sub_industry = Column(String(128))
    scale = Column(String(32))  # 中小型|中型|大型|特大型
    contact = Column(JSON, default=dict)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    documents = relationship("Document", back_populates="customer")


class Document(Base):
    __tablename__ = "esg_knowledge_documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(512), nullable=False)
    framework = Column(String(64), index=True)  # GRI|CASS|TCFD|ISSB|SASB|ISO|other
    doc_type = Column(String(32), default="standard")  # standard|whitepaper|guide|report|customer
    visibility = Column(String(16), default="public")  # public|internal|customer
    customer_id = Column(String(36), ForeignKey("esg_knowledge_customers.id"), index=True)
    tags = Column(JSON, default=list)
    metadata_ = Column("metadata", JSON, default=dict)
    summary = Column(Text)
    chunk_count = Column(Integer, default=0)
    status = Column(String(16), default="processing")  # processing|ready|failed
    file_path = Column(String(512))
    content_hash = Column(String(128))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

    customer = relationship("Customer", back_populates="documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "esg_knowledge_chunks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    doc_id = Column(String(36), ForeignKey("esg_knowledge_documents.id"), nullable=False, index=True)
    customer_id = Column(String(36), index=True)  # denormalized for fast filtering
    text = Column(Text, nullable=False)
    section = Column(String(256))
    page = Column(Integer)
    chunk_index = Column(Integer)
    token_count = Column(Integer)
    embedding = Column(JSON)  # vector as JSON array (1536 dim)
    tsvector = Column(Text)  # full-text search vector (stored as text)
    metadata_ = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime, server_default=func.now())

    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("ix_esg_knowledge_chunks_customer", "customer_id"),
    )


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class CustomerCreate(BaseModel):
    name: str
    short_name: Optional[str] = None
    stock_code: Optional[str] = None
    industry: Optional[str] = None
    sub_industry: Optional[str] = None
    scale: Optional[str] = None
    contact: Optional[dict[str, Any]] = Field(default_factory=dict)
    tags: Optional[list[str]] = Field(default_factory=list)


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    short_name: Optional[str] = None
    stock_code: Optional[str] = None
    industry: Optional[str] = None
    sub_industry: Optional[str] = None
    scale: Optional[str] = None
    contact: Optional[dict[str, Any]] = None
    tags: Optional[list[str]] = None


class CustomerResponse(BaseModel):
    id: str
    name: str
    short_name: Optional[str] = None
    stock_code: Optional[str] = None
    industry: Optional[str] = None
    sub_industry: Optional[str] = None
    scale: Optional[str] = None
    contact: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class DocumentCreate(BaseModel):
    title: str
    framework: Optional[str] = None
    doc_type: str = "standard"
    visibility: str = "public"
    customer_id: Optional[str] = None
    tags: Optional[list[str]] = Field(default_factory=list)
    metadata_: Optional[dict[str, Any]] = Field(default_factory=dict, alias="metadata")
    content: Optional[str] = None  # inline content for import


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    framework: Optional[str] = None
    doc_type: Optional[str] = None
    visibility: Optional[str] = None
    customer_id: Optional[str] = None
    tags: Optional[list[str]] = None
    metadata_: Optional[dict[str, Any]] = Field(default=None, alias="metadata")
    summary: Optional[str] = None


class DocumentResponse(BaseModel):
    id: str
    title: str
    framework: Optional[str] = None
    doc_type: str = "standard"
    visibility: str = "public"
    customer_id: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")
    summary: Optional[str] = None
    chunk_count: int = 0
    status: str = "processing"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True, "populate_by_name": True}


class ChunkResponse(BaseModel):
    id: str
    doc_id: str
    customer_id: Optional[str] = None
    text: str
    section: Optional[str] = None
    page: Optional[int] = None
    chunk_index: Optional[int] = None
    token_count: Optional[int] = None
    metadata_: dict[str, Any] = Field(default_factory=dict, alias="metadata")

    model_config = {"from_attributes": True, "populate_by_name": True}


class SearchRequest(BaseModel):
    query: str
    customer_id: Optional[str] = None
    framework: Optional[str] = None
    top_k: int = 10


class KeywordSearchRequest(SearchRequest):
    pass


class SemanticSearchRequest(SearchRequest):
    query_embedding: Optional[list[float]] = None


class HybridSearchRequest(SearchRequest):
    query_embedding: Optional[list[float]] = None
    keyword_weight: float = 0.3
    semantic_weight: float = 0.7


class SearchResult(BaseModel):
    chunk_id: str
    doc_id: str
    doc_title: str
    text: str
    score: float
    match_type: str  # keyword|semantic|hybrid
    customer_id: Optional[str] = None


class RAGRetrieveRequest(BaseModel):
    question: str
    customer_id: Optional[str] = None
    top_k: int = 5
    max_tokens: int = 4000


class RAGContextItem(BaseModel):
    source: str
    text: str
    relevance: float


class RAGContextResponse(BaseModel):
    context: list[RAGContextItem]
    total_tokens: int


class BatchImportRequest(BaseModel):
    file_paths: list[str]
    framework: Optional[str] = None
    doc_type: str = "standard"
    customer_id: Optional[str] = None


class BatchImportResponse(BaseModel):
    imported: int
    failed: int
    document_ids: list[str]


class StatsResponse(BaseModel):
    total_documents: int
    total_chunks: int
    total_customers: int
    documents_by_framework: dict[str, int]
    documents_by_status: dict[str, int]
