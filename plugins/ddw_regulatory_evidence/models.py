"""SQLAlchemy ORM models for Regulatory Evidence plugin."""
from __future__ import annotations

import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    __allow_unmapped__ = True


class RegulatoryDocument(Base):
    """Regulatory document or evidence item."""
    __tablename__ = "re_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False)
    content = Column(Text, nullable=False)
    jurisdiction = Column(String(16), nullable=False)  # CN/EU/US/JP/KR/INT
    authority = Column(String(64), nullable=False)  # NHC/EU_Commission/EFSA/FDA/Codex
    doc_type = Column(String(32), nullable=False)  # regulation/guidance/approval/certificate/evidence/report
    category = Column(String(64), default="general")  # novel_food/food_additive/haccp/gmp/labeling/claim
    reference_number = Column(String(128), default="")  # regulation number, approval number
    effective_date = Column(String(32), default="")
    tags = Column(JSON, nullable=True)
    source_url = Column(String(512), default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class EvidenceChain(Base):
    """Evidence chain linking regulatory requirements to company compliance."""
    __tablename__ = "re_evidence_chains"

    id = Column(Integer, primary_key=True, autoincrement=True)
    requirement = Column(Text, nullable=False)  # what the regulation requires
    regulation_id = Column(Integer, ForeignKey("re_documents.id"), nullable=True)
    product_name = Column(String(128), default="")
    compliance_status = Column(String(16), default="pending")  # compliant/partial/non_compliant/pending
    evidence_description = Column(Text, default="")
    evidence_documents = Column(JSON, nullable=True)  # list of document references
    gaps = Column(Text, default="")
    action_plan = Column(Text, default="")
    responsible = Column(String(128), default="")
    due_date = Column(String(32), default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    regulation: "RegulatoryDocument" = relationship("RegulatoryDocument")
