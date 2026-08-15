"""SQLAlchemy ORM models for CAPA Workflow plugin."""
from __future__ import annotations

import datetime
from typing import List

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    __allow_unmapped__ = True


class CAPA(Base):
    """CAPA (Corrective and Preventive Action) record."""
    __tablename__ = "capa_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    capa_number = Column(String(32), nullable=False, unique=True)  # CAPA-YYYY-NNN
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=False)
    source = Column(String(32), nullable=False)  # deviation/complaint/audit/oos/oot/regulatory/internal
    severity = Column(String(16), default="major")  # critical/major/minor
    category = Column(String(64), default="general")
    status = Column(String(32), default="open")  # open/investigation/action/verification/closed/rejected
    root_cause = Column(Text, default="")
    root_cause_method = Column(String(32), default="")  # 5why/fishbone/both
    corrective_action = Column(Text, default="")
    preventive_action = Column(Text, default="")
    effectiveness_check = Column(Text, default="")
    assigned_to = Column(String(128), default="")
    due_date = Column(DateTime, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    created_by = Column(String(128), default="system")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    history: List["CAPAHistory"] = relationship("CAPAHistory", back_populates="capa",
                                                 order_by="CAPAHistory.created_at")


class CAPAHistory(Base):
    """CAPA status change history / audit trail."""
    __tablename__ = "capa_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    capa_id = Column(Integer, ForeignKey("capa_records.id"), nullable=False)
    from_status = Column(String(32), default="")
    to_status = Column(String(32), nullable=False)
    comment = Column(Text, default="")
    changed_by = Column(String(128), default="system")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    capa: "CAPA" = relationship("CAPA", back_populates="history")
