"""DDW 岗位设计器 ORM 模型（v1.0）。

单表：PositionDesign — 岗位四维设计（Outcome / 人的责任 / Agent Stack / Decision Rights）
外加 v2.0 扩展字段（能力标准 / 风险管控）。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database.models import Base, TenantMixin, TimestampMixin

# BigInteger 在 SQLite 不支持 -> 退化到 Integer
BigInt = BigInteger().with_variant(Integer(), "sqlite")


# ---------------------------------------------------------------------------
# 标准部门列表（与 ddw_opc_departments 保持一致）
# ---------------------------------------------------------------------------

STANDARD_DEPARTMENTS: list[str] = [
    "销售部", "市场部", "客服部", "生产部", "研发部",
    "质量部", "采购部", "人力资源部", "财务部", "IT 部", "行政部",
]

DECISION_TYPES: list[str] = ["auto", "suggest", "human", "escalate"]

DECISION_TYPE_LABELS = {
    "auto": "Agent 自动",
    "suggest": "Agent 建议",
    "human": "人工决策",
    "escalate": "升级审批",
}


class PositionDesign(Base, TenantMixin, TimestampMixin):
    """AI 原生岗位设计主表。"""

    __tablename__ = "position_designs"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)

    # 基础信息
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True,
                                       comment="岗位名称")
    department: Mapped[Optional[str]] = mapped_column(String(100), index=True,
                                                       comment="所属部门")
    report_to: Mapped[Optional[str]] = mapped_column(String(100),
                                                      comment="汇报对象")
    company: Mapped[Optional[str]] = mapped_column(String(200),
                                                   comment="公司/组织")
    description: Mapped[Optional[str]] = mapped_column(Text,
                                                       comment="岗位描述（传统 JD 兼容）")

    # 维度 1: Outcome（业务结果列表）
    outcomes: Mapped[list] = mapped_column(JSON, default=list, nullable=False,
                                            comment="业务结果列表（Outcome Ownership）")

    # 维度 2: 人的责任
    human_responsibilities: Mapped[list] = mapped_column(JSON, default=list, nullable=False,
                                                          comment="人的责任列表")

    # 维度 3: Agent Stack
    agent_stack: Mapped[list] = mapped_column(JSON, default=list, nullable=False,
                                               comment="Agent 组合列表")

    # 维度 4: Decision Rights（决策权限矩阵）
    decision_rights: Mapped[list] = mapped_column(JSON, default=list, nullable=False,
                                                   comment="决策权限矩阵")

    # 维度 5: 能力标准（v2.0）
    human_capability: Mapped[Optional[str]] = mapped_column(Text,
                                                             comment="人类核心能力要求")
    agent_capability: Mapped[Optional[str]] = mapped_column(Text,
                                                             comment="Agent 能力边界")
    handoff_protocol: Mapped[Optional[str]] = mapped_column(Text,
                                                             comment="人机交接协议")

    # 维度 6: 风险管控（v2.0）
    risk_controls: Mapped[list] = mapped_column(JSON, default=list,
                                                 comment="风控措施列表")

    # 元信息
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False,
                                        comment="draft / active / archived")
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False,
                                          comment="版本号（每次更新 +1）")
    tags: Mapped[Optional[list]] = mapped_column(JSON, default=list,
                                                   comment="扩展标签")

    # 审计
    created_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(BigInt, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PositionDesign id={self.id} name={self.name!r} dept={self.department!r}>"


__all__ = [
    "PositionDesign",
    "STANDARD_DEPARTMENTS",
    "DECISION_TYPES",
    "DECISION_TYPE_LABELS",
]
