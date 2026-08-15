"""SQLAlchemy ORM models for Quality Knowledge plugin."""
from __future__ import annotations

import datetime

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    __allow_unmapped__ = True


class KnowledgeDocument(Base):
    """A knowledge base document (standard, SOP, case, regulation)."""
    __tablename__ = "qk_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False)
    content = Column(Text, nullable=False)
    doc_type = Column(String(32), nullable=False, index=True)  # standard/sop/case/regulation/guide
    category = Column(String(64), default="general")  # haccp/iso22000/fssc22000/gmp/novel_food/efsa/nhc
    tags = Column(JSON, nullable=True)  # list of tags
    source = Column(String(256), default="")  # source URL or document reference
    embedding = Column(Text, nullable=True)  # JSON serialized embedding vector
    relevance_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class SearchLog(Base):
    """Search query log for analytics."""
    __tablename__ = "qk_search_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(Text, nullable=False)
    results_count = Column(Integer, default=0)
    clicked_doc_id = Column(Integer, nullable=True)
    user_id = Column(String(128), default="anonymous")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
