"""FactSheet 数据结构 + 序列化 + 事实抽取辅助。

C 方案的核心：把"标书事实"从 LLM 上下文中剥离，落到结构化数据。
每章生成前 → 注入 FactSheet；每章生成后 → 抽取新事实回填。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------


@dataclass
class PersonnelFact:
    """人员事实。"""
    role: str  # 项目经理 / 技术负责人 / 设计负责人
    name: str
    title: Optional[str] = None  # 高级工程师 / 注册结构师
    certs: List[str] = field(default_factory=list)


@dataclass
class DateFact:
    """日期事实。"""
    key: str  # 开工日 / 竣工日 / 关键里程碑
    value: str  # ISO 格式


@dataclass
class MetricFact:
    """数值事实。"""
    key: str  # 单方造价 / 总投资 / 工期 / 混凝土用量
    value: float
    unit: str = ""


@dataclass
class FactSheet:
    """标书事实表 — 跨章一致性的锚点。

    所有跨章节必须一致的事实，集中在这里：
    - 基础事实：项目名/客户/类型/金额/截止/结构类型/层数/面积
    - 人员：项目经理 + 关键岗位
    - 日期：关键里程碑
    - 数值：核心经济/技术指标
    - 风格基线：写作风格描述
    """

    # 基础
    project_name: str = ""
    client_name: str = ""
    project_type: str = ""  # 住宅/商业/工业/市政
    estimated_amount: float = 0.0
    bid_deadline: Optional[str] = None  # ISO
    structure_type: str = ""  # 框架/框剪/钢结构
    floor_count: int = 0
    area_sqm: float = 0.0

    # 人员
    personnel: List[PersonnelFact] = field(default_factory=list)

    # 日期
    dates: List[DateFact] = field(default_factory=list)

    # 数值
    metrics: List[MetricFact] = field(default_factory=list)

    # 风格基线
    style_baseline: str = ""  # "本标书采用保守、稳妥、成熟的表达..."

    # 一致性冲突记录（阶段 3 用）
    conflicts: List[Dict[str, Any]] = field(default_factory=list)

    # 元数据
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_markdown(self) -> str:
        """序列化为 Markdown（注入 LLM prompt 用）。"""
        lines: List[str] = ["# 标书事实表（FactSheet）", ""]
        lines.append("> 下列事实为硬约束，所有章节必须严格遵循，不允许更改数值、日期、名称。")
        lines.append("")
        lines.append("## 基础事实")
        lines.append(f"- 项目名称：{self.project_name}")
        lines.append(f"- 客户名称：{self.client_name}")
        lines.append(f"- 项目类型：{self.project_type}")
        if self.estimated_amount:
            lines.append(f"- 估算金额：{self.estimated_amount:,.0f} 元")
        if self.bid_deadline:
            lines.append(f"- 投标截止：{self.bid_deadline}")
        if self.structure_type:
            lines.append(f"- 结构类型：{self.structure_type}")
        if self.floor_count:
            lines.append(f"- 层数：{self.floor_count}")
        if self.area_sqm:
            lines.append(f"- 建筑面积：{self.area_sqm:,.0f} ㎡")
        if self.style_baseline:
            lines.append("")
            lines.append("## 风格基线")
            lines.append(self.style_baseline)
        if self.personnel:
            lines.append("")
            lines.append("## 关键人员")
            for p in self.personnel:
                lines.append(f"- {p.role}：{p.name}" + (f"（{p.title}）" if p.title else ""))
                if p.certs:
                    lines.append(f"  证书：{', '.join(p.certs)}")
        if self.dates:
            lines.append("")
            lines.append("## 关键日期")
            for d in self.dates:
                lines.append(f"- {d.key}：{d.value}")
        if self.metrics:
            lines.append("")
            lines.append("## 关键指标")
            for m in self.metrics:
                lines.append(f"- {m.key}：{m.value:,.2f} {m.unit}".rstrip())
        if self.conflicts:
            lines.append("")
            lines.append("## ⚠️ 一致性冲突（待解决）")
            for c in self.conflicts:
                lines.append(f"- [{c.get('severity', 'warn')}] {c.get('description', '')}")
        return "\n".join(lines)

    def update_from_section(self, section_content: str, section_name: str) -> List[str]:
        """从章节内容中抽取新事实，回填到 FactSheet。

        返回：本次更新的事实字段名列表。
        """
        updated: List[str] = []
        # 抽取人员
        personnel = extract_personnel(section_content)
        for p in personnel:
            if not any(existing.role == p.role and existing.name == p.name for existing in self.personnel):
                self.personnel.append(p)
                updated.append(f"personnel:{p.role}={p.name}")
        # 抽取日期
        dates = extract_dates(section_content)
        for d in dates:
            if not any(existing.key == d.key for existing in self.dates):
                self.dates.append(d)
                updated.append(f"date:{d.key}={d.value}")
        # 抽取指标
        metrics = extract_metrics(section_content, self.project_type)
        for m in metrics:
            if not any(existing.key == m.key for existing in self.metrics):
                self.metrics.append(m)
                updated.append(f"metric:{m.key}={m.value}{m.unit}")
        if updated:
            self.updated_at = datetime.utcnow().isoformat()
        return updated


# ---------------------------------------------------------------------------
# 抽取函数（规则化，从章节文本提取事实）
# ---------------------------------------------------------------------------


_PERSONNEL_RE = re.compile(
    r"(项目经理|技术负责人|设计负责人|总工程师|项目总监|商务负责人|技术总监|质量负责人|安全负责人)[：:]\s*([\u4e00-\u9fa5]{2,4})"
)
_DATE_RE = re.compile(
    r"(开工日?|竣工日?|交付日?|截止日?|起止时间|总工期)[：:为]?\s*(\d{4}[-./年]\d{1,2}[-./月]?\d{1,2}?日?)"
)
_METRIC_RE = re.compile(
    r"(单方造价|总投资|总造价|合同金额|总工期|工期|建筑面积|层数|高度|混凝土用量|钢筋用量|容积率|绿地率)[：:为]?\s*([\d,\.]+)\s*(元/㎡|元/m²|元|㎡|m²|米|m|月|天|万吨|吨)?"
)


def extract_personnel(text: str) -> List[PersonnelFact]:
    out: List[PersonnelFact] = []
    seen = set()
    for m in _PERSONNEL_RE.finditer(text):
        role = m.group(1)
        name = m.group(2)
        if (role, name) in seen:
            continue
        seen.add((role, name))
        out.append(PersonnelFact(role=role, name=name))
    return out


def extract_dates(text: str) -> List[DateFact]:
    out: List[DateFact] = []
    seen = set()
    for m in _DATE_RE.finditer(text):
        key = m.group(1)
        val = m.group(2)
        if key in seen:
            continue
        seen.add(key)
        out.append(DateFact(key=key, value=val))
    return out


def extract_metrics(text: str, project_type: str = "") -> List[MetricFact]:
    out: List[MetricFact] = []
    seen = set()
    for m in _METRIC_RE.finditer(text):
        key = m.group(1)
        try:
            v = float(m.group(2).replace(",", ""))
        except ValueError:
            continue
        unit = m.group(3) or ""
        if key in seen:
            continue
        seen.add(key)
        out.append(MetricFact(key=key, value=v, unit=unit))
    return out


# ---------------------------------------------------------------------------
# 序列化辅助
# ---------------------------------------------------------------------------


def fact_sheet_from_dict(d: Dict[str, Any]) -> FactSheet:
    """从 dict 构造 FactSheet（处理嵌套类型）。"""
    p_list = [PersonnelFact(**p) for p in d.get("personnel", [])]
    d_list = [DateFact(**x) for x in d.get("dates", [])]
    m_list = [MetricFact(**x) for x in d.get("metrics", [])]
    fs = FactSheet(
        project_name=d.get("project_name", ""),
        client_name=d.get("client_name", ""),
        project_type=d.get("project_type", ""),
        estimated_amount=d.get("estimated_amount", 0.0),
        bid_deadline=d.get("bid_deadline"),
        structure_type=d.get("structure_type", ""),
        floor_count=d.get("floor_count", 0),
        area_sqm=d.get("area_sqm", 0.0),
        personnel=p_list,
        dates=d_list,
        metrics=m_list,
        style_baseline=d.get("style_baseline", ""),
        conflicts=d.get("conflicts", []),
        created_at=d.get("created_at", datetime.utcnow().isoformat()),
        updated_at=d.get("updated_at", datetime.utcnow().isoformat()),
    )
    return fs


def fact_sheet_to_json(fs: FactSheet) -> str:
    return json.dumps(fs.to_dict(), ensure_ascii=False, default=str)


__all__ = [
    "DateFact",
    "FactSheet",
    "MetricFact",
    "PersonnelFact",
    "extract_dates",
    "extract_metrics",
    "extract_personnel",
    "fact_sheet_from_dict",
    "fact_sheet_to_json",
]
