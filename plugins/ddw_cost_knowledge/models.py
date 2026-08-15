"""DDW 造价知识库 ORM 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database.session import Base
from core.database.tenant_filter import TENANT_AWARE_ATTR

# 兼容 SQLite
BigInt = Integer()


class CostDocument(Base):
    """造价文件主表。"""

    __tablename__ = "cost_documents"
    __table_args__ = {"extend_existing": True}
    __tenant_aware__ = True  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 历史造价文件/定额/清单/指标
    project_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    project_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)  # 住宅/商业/工业/市政
    total_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    area: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # ㎡
    unit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 元/㎡
    extracted_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # LLM 提炼
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)  # pending/processed/failed
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class CostEstimate(Base):
    """造价估算记录。"""

    __tablename__ = "cost_estimates"
    __table_args__ = {"extend_existing": True}
    __tenant_aware__ = True  # type: ignore[assignment]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInt, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)

    project_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    project_type: Mapped[str] = mapped_column(String(50), nullable=False)
    area: Mapped[float] = mapped_column(Float, nullable=False)
    floor_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    structure_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 框架/框剪/钢结构

    estimate_result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    reference_docs: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # 参考 doc id 列表
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


__all__ = [
    "TENANT_AWARE_ATTR",
    "CostDocument",
    "CostEstimate",
]
