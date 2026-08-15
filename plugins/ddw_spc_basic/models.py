"""SQLAlchemy ORM models for SPC Basic plugin."""
from __future__ import annotations

import datetime

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    __allow_unmapped__ = True


class ControlChart(Base):
    """Control chart analysis record."""
    __tablename__ = "spc_control_charts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chart_type = Column(String(16), nullable=False)  # I-MR / Xbar-R / Xbar-S / p / np / c / u
    parameter_name = Column(String(128), nullable=False)
    product_name = Column(String(128), default="")
    data_points = Column(JSON, nullable=False)  # list of float
    center_line = Column(Float, nullable=False)
    ucl = Column(Float, nullable=False)  # Upper Control Limit
    lcl = Column(Float, nullable=False)  # Lower Control Limit
    usl = Column(Float, nullable=True)  # Upper Spec Limit
    lsl = Column(Float, nullable=True)  # Lower Spec Limit
    violations = Column(JSON, nullable=True)  # list of rule violations
    cp = Column(Float, nullable=True)
    cpk = Column(Float, nullable=True)
    pp = Column(Float, nullable=True)
    ppk = Column(Float, nullable=True)
    interpretation = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class ProcessCapability(Base):
    """Process capability study record."""
    __tablename__ = "spc_capability"

    id = Column(Integer, primary_key=True, autoincrement=True)
    parameter_name = Column(String(128), nullable=False)
    product_name = Column(String(128), default="")
    sample_size = Column(Integer, nullable=False)
    mean = Column(Float, nullable=False)
    std_dev = Column(Float, nullable=False)
    usl = Column(Float, nullable=True)
    lsl = Column(Float, nullable=True)
    cp = Column(Float, nullable=True)
    cpk = Column(Float, nullable=True)
    pp = Column(Float, nullable=True)
    ppk = Column(Float, nullable=True)
    capability_grade = Column(String(8), default="")  # A/B/C/D
    interpretation = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
