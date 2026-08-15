"""SQLAlchemy ORM models for Quality Assistant plugin."""
from __future__ import annotations

import datetime

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    __allow_unmapped__ = True


class QualityDocument(Base):
    """Generated quality document (8D, CAPA draft, deviation, complaint reply)."""
    __tablename__ = "qa_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_type = Column(String(32), nullable=False, index=True)  # 8d/capa/deviation/complaint/5why
    title = Column(String(256), nullable=False)
    content = Column(Text, nullable=False)
    input_data = Column(JSON, nullable=True)  # original input parameters
    status = Column(String(16), default="draft")  # draft/reviewed/approved/archived
    created_by = Column(String(128), default="system")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class QualityTemplate(Base):
    """Reusable quality document templates."""
    __tablename__ = "qa_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, unique=True)
    doc_type = Column(String(32), nullable=False, index=True)
    template_content = Column(Text, nullable=False)
    description = Column(Text, default="")
    industry = Column(String(64), default="general")  # food/pharma/electronics/general
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class FiveWhyAnalysis(Base):
    """5-Why root cause analysis records."""
    __tablename__ = "qa_five_why"

    id = Column(Integer, primary_key=True, autoincrement=True)
    problem_description = Column(Text, nullable=False)
    why_chain = Column(JSON, nullable=False)  # list of {"why": "...", "answer": "..."}
    root_cause = Column(Text, nullable=False)
    corrective_action = Column(Text, default="")
    document_id = Column(Integer, nullable=True)  # link to QualityDocument
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
