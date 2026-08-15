"""碳硅协同数据模型（ddw_flow_designer）。

表：
- flow_definitions  流程定义（草稿/待审/已发布/已停用）
- flow_versions     版本历史（每次发布存档 dag_json）
- flow_reviews      跨部门审核记录
- flow_runs         执行记录（真实 LLM 串行执行）
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from core.database.session import Base


class FlowDefinition(Base):
    __tablename__ = "flow_definitions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Integer, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, default="")
    department_id = Column(Integer, nullable=True)          # 所属部门（null=公司级）
    created_by = Column(Integer, nullable=False)
    scope = Column(String(20), default="department")        # department / cross_department
    status = Column(String(30), default="draft")            # draft/pending_review/published/deprecated
    version = Column(String(20), default="0.0.0")           # semver
    dag_json = Column(Text, nullable=False, default="{}")   # {nodes:[], edges:[]}
    is_enabled = Column(Boolean, default=False)
    total_runs = Column(Integer, default=0)
    monthly_runs = Column(Integer, default=0)
    avg_duration_ms = Column(Integer, default=0)
    last_run_at = Column(DateTime, nullable=True)
    deprecated_at = Column(DateTime, nullable=True)
    input_spec = Column(Text, nullable=True)
    output_spec = Column(Text, nullable=True)
    cross_dept_review_config = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FlowVersion(Base):
    __tablename__ = "flow_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    flow_id = Column(Integer, nullable=False, index=True)
    version = Column(String(20), nullable=False)
    dag_json = Column(Text, nullable=False, default="{}")
    changelog = Column(Text, default="")
    published_by = Column(Integer, nullable=False)
    published_at = Column(DateTime, default=datetime.utcnow)


class FlowReview(Base):
    __tablename__ = "flow_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    flow_id = Column(Integer, nullable=False, index=True)
    department_id = Column(Integer, nullable=False)         # 需要审核的部门
    reviewer_id = Column(Integer, nullable=True)
    status = Column(String(20), default="pending")          # pending/approved/rejected
    comment = Column(Text, default="")
    checklist_results = Column(Text, default="[]")
    skill_merger_approved = Column(Boolean, default=False)
    review_deadline = Column(DateTime, nullable=True)
    remind_count = Column(Integer, default=0)
    reviewed_at = Column(DateTime, nullable=True)


class FlowRun(Base):
    __tablename__ = "flow_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    flow_id = Column(Integer, nullable=False, index=True)
    version = Column(String(20), nullable=False)
    status = Column(String(20), default="running")          # running/success/failed/input_rejected/output_rejected/pending_human_fix/draft_incomplete
    result = Column(Text, default="{}")                     # {node_id: output, ...}
    error = Column(Text, default="")
    created_by = Column(Integer, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


__all__ = ["FlowDefinition", "FlowVersion", "FlowReview", "FlowRun"]
