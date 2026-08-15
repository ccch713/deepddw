"""文档生成器：基于知识库 + 模板生成企业文档。

支持模板类型：
- 8D 报告（8 Disciplines Problem Solving）
- CAPA（Corrective and Preventive Action）
- 质量报警（Quality Alert）
- COA（Certificate of Analysis）
- FMEA（Failure Mode and Effects Analysis）
- 自定义模板
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import DocumentTemplate, GeneratedDocument
from .hierarchical_retriever import RetrievalChunk

logger = logging.getLogger(__name__)


# ─── 内置模板 ───

BUILTIN_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "8d": {
        "name": "8D 报告",
        "template_type": "8d",
        "industry": "general",
        "description": "8 Disciplines Problem Solving 报告模板",
        "content_template": """# 8D 问题解决报告

## 基本信息
- **报告编号**: {{ report_id }}
- **日期**: {{ date }}
- **产品/过程**: {{ product_name }}
- **问题描述**: {{ problem_description }}
- **严重程度**: {{ severity }}
- **报告人**: {{ reporter }}
- **客户**: {{ customer }}

---

## D1 - 建立团队
- **团队负责人**: {{ team_leader }}
- **团队成员**: {{ team_members }}
- **职责分工**: {{ roles }}

---

## D2 - 问题描述
{{ problem_detail }}

### 问题数据
{{ problem_data }}

---

## D3 - 临时遏制措施
{{ containment_actions }}

---

## D4 - 根本原因分析
{{ root_cause_analysis }}

### 鱼骨图分析
{{ fishbone_analysis }}

### 5-Why 分析
{{ five_why_analysis }}

---

## D5 - 永久纠正措施
{{ corrective_actions }}

---

## D6 - 实施和验证
{{ implementation_verification }}

---

## D7 - 预防措施
{{ preventive_actions }}

---

## D8 - 团队祝贺
{{ conclusion }}

---

## 知识库参考
{% for ref in knowledge_refs %}
- [来源{{ loop.index }}] {{ ref.section_title }} (相似度: {{ "%.2f"|format(ref.score) }})
{% endfor %}
""",
        "metadata_schema": {
            "required": ["product_name", "problem_description", "severity"],
            "optional": ["customer", "reporter", "team_leader"],
        },
    },
    "capa": {
        "name": "CAPA 纠正预防措施",
        "template_type": "capa",
        "industry": "general",
        "description": "Corrective and Preventive Action 报告模板",
        "content_template": """# CAPA 纠正预防措施报告

## 基本信息
- **CAPA 编号**: {{ capa_id }}
- **日期**: {{ date }}
- **来源**: {{ source }} (客户投诉/内部审计/管理评审/偏差)
- **严重程度**: {{ severity }}
- **负责人**: {{ responsible }}

---

## 1. 问题描述
{{ problem_description }}

## 2. 影响评估
{{ impact_assessment }}

## 3. 根本原因
{{ root_cause }}

## 4. 纠正措施 (Corrective Actions)
{{ corrective_actions }}

### 实施计划
| 序号 | 措施 | 负责人 | 截止日期 | 状态 |
|-----|------|-------|---------|------|
{% for action in corrective_plan %}
| {{ loop.index }} | {{ action.measure }} | {{ action.owner }} | {{ action.deadline }} | {{ action.status }} |
{% endfor %}

## 5. 预防措施 (Preventive Actions)
{{ preventive_actions }}

## 6. 有效性验证
{{ effectiveness_verification }}

## 7. 关闭条件
{{ closure_criteria }}

---

## 知识库参考
{% for ref in knowledge_refs %}
- [来源{{ loop.index }}] {{ ref.section_title }}
{% endfor %}
""",
    },
    "quality_alert": {
        "name": "质量报警",
        "template_type": "quality_alert",
        "industry": "food",
        "description": "食品行业质量报警模板",
        "content_template": """# 质量报警通知

## 报警信息
- **报警编号**: {{ alert_id }}
- **日期**: {{ date }}
- **报警级别**: {{ alert_level }} (红色/橙色/黄色)
- **产品**: {{ product_name }}
- **批次号**: {{ batch_number }}
- **涉及数量**: {{ quantity }}

---

## 1. 报警触发原因
{{ trigger_reason }}

## 2. 检测数据
{{ inspection_data }}

### 关键指标
| 指标 | 标准值 | 实测值 | 偏差 |
|-----|-------|-------|------|
{% for metric in key_metrics %}
| {{ metric.name }} | {{ metric.standard }} | {{ metric.actual }} | {{ metric.deviation }} |
{% endfor %}

## 3. 风险评估
{{ risk_assessment }}

## 4. 立即处置措施
{{ immediate_actions }}

## 5. 通知范围
- [ ] 质量部
- [ ] 生产部
- [ ] 销售部
- [ ] 客户: {{ customer }}
- [ ] 监管部门 (如需要)

## 6. 后续跟进
{{ follow_up }}

---

## 知识库参考
{% for ref in knowledge_refs %}
- [来源{{ loop.index }}] {{ ref.section_title }}
{% endfor %}
""",
    },
    "coa": {
        "name": "检验报告 (COA)",
        "template_type": "coa",
        "industry": "food",
        "description": "Certificate of Analysis 检验报告模板",
        "content_template": """# 检验报告 (COA)

## 产品信息
- **产品名称**: {{ product_name }}
- **产品规格**: {{ specification }}
- **批次号**: {{ batch_number }}
- **生产日期**: {{ production_date }}
- **检验日期**: {{ inspection_date }}
- **有效期至**: {{ expiry_date }}

---

## 检验结果

| 检验项目 | 标准要求 | 检验结果 | 单位 | 判定 |
|---------|---------|---------|------|------|
{% for item in inspection_items %}
| {{ item.name }} | {{ item.standard }} | {{ item.result }} | {{ item.unit }} | {{ item.pass }} |
{% endfor %}

## 微生物检验
{{ microbiology_results }}

## 重金属检验
{{ heavy_metal_results }}

## 结论
{{ conclusion }}

---

**检验员**: {{ inspector }}
**审核人**: {{ reviewer }}
**日期**: {{ date }}
""",
    },
    "fmea": {
        "name": "FMEA 失效模式分析",
        "template_type": "fmea",
        "industry": "general",
        "description": "Failure Mode and Effects Analysis 模板",
        "content_template": """# FMEA 失效模式与影响分析

## 基本信息
- **FMEA 编号**: {{ fmea_id }}
- **产品/过程**: {{ process_name }}
- **日期**: {{ date }}
- **团队**: {{ team }}

---

## 失效模式分析表

| 序号 | 过程步骤 | 潜在失效模式 | 潜在影响 | 严重度(S) | 潜在原因 | 发生度(O) | 现有控制 | 探测度(D) | RPN | 建议措施 |
|-----|---------|------------|---------|----------|---------|----------|---------|----------|-----|---------|
{% for mode in failure_modes %}
| {{ loop.index }} | {{ mode.step }} | {{ mode.failure_mode }} | {{ mode.effect }} | {{ mode.severity }} | {{ mode.cause }} | {{ mode.occurrence }} | {{ mode.controls }} | {{ mode.detection }} | {{ mode.rpn }} | {{ mode.action }} |
{% endfor %}

## 高风险项 (RPN > {{ rpn_threshold }})
{{ high_risk_analysis }}

## 改进措施
{{ improvement_actions }}

---

## 知识库参考
{% for ref in knowledge_refs %}
- [来源{{ loop.index }}] {{ ref.section_title }}
{% endfor %}
""",
    },
}


class DocumentGenerator:
    """文档生成器。"""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

    async def init_builtin_templates(self) -> int:
        """初始化内置模板到数据库。"""
        count = 0
        for tpl_data in BUILTIN_TEMPLATES.values():
            existing = await self.db.execute(
                select(DocumentTemplate).where(DocumentTemplate.name == tpl_data["name"])
            )
            if existing.scalar_one_or_none() is None:
                tpl = DocumentTemplate(**tpl_data)
                self.db.add(tpl)
                count += 1
        await self.db.flush()
        return count

    async def generate(
        self,
        template_name: str,
        variables: Dict[str, Any],
        knowledge_refs: Optional[List[RetrievalChunk]] = None,
        title: Optional[str] = None,
        knowledge_bucket: Optional[str] = None,
    ) -> GeneratedDocument:
        """基于模板 + 变量 + 知识库引用生成文档。"""
        from sqlalchemy import select

        # 查找模板（支持 name 或 template_type/key 匹配）
        stmt = select(DocumentTemplate).where(
            (DocumentTemplate.name == template_name)
            | (DocumentTemplate.template_type == template_name)
        )
        result = await self.db.execute(stmt)
        template = result.scalars().first()
        if template is None:
            # 检查内置模板
            builtin = BUILTIN_TEMPLATES.get(template_name)
            if builtin is None:
                raise ValueError(f"模板不存在: {template_name}")
            # 自动创建
            template = DocumentTemplate(**builtin)
            self.db.add(template)
            await self.db.flush()

        # 渲染模板
        try:
            from jinja2 import Template
            tpl = Template(template.content_template)
            content = tpl.render(
                **variables,
                knowledge_refs=[
                    {
                        "section_title": c.section_title,
                        "score": c.score,
                        "content": c.content[:200],
                    }
                    for c in (knowledge_refs or [])
                ],
                date=datetime.now().strftime("%Y-%m-%d"),
                report_id=str(uuid.uuid4())[:8].upper(),
            )
        except ImportError:
            # 无 Jinja2 时的简单替换
            content = template.content_template
            for key, value in variables.items():
                content = content.replace("{{ " + key + " }}", str(value))

        # 保存生成的文档
        doc = GeneratedDocument(
            template_id=template.id,
            title=title or f"{template.name} - {datetime.now().strftime('%Y%m%d')}",
            content=content,
            doc_type=template.template_type,
            knowledge_bucket=knowledge_bucket,
            source_document_ids=[c.chunk_id for c in (knowledge_refs or [])],
        )
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def list_templates(self) -> List[Dict[str, Any]]:
        """列出所有可用模板。"""
        from sqlalchemy import select
        result = await self.db.execute(select(DocumentTemplate))
        templates = result.scalars().all()
        return [
            {
                "id": t.id, "name": t.name, "template_type": t.template_type,
                "industry": t.industry, "description": t.description,
            }
            for t in templates
        ]
