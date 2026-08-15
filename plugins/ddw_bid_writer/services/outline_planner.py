"""阶段 1：Outline Planner（生成标书大纲 + 风格基线 + FactSheet 初始化）。

输入：项目元数据 + 风格 + 可选模板
输出：大纲（章节标题 + 摘要）+ 初始化 FactSheet + 风格基线
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

from plugins.ddw_bid_writer.services.fact_sheet import (
    FactSheet,
    extract_personnel,
)
from plugins.ddw_bid_writer.services.mcp_client import get_mcp_client

logger = logging.getLogger(__name__)


# 各 doc_type 的默认章节骨架（兜底用，不调 LLM 也能跑）
DEFAULT_SECTIONS = {
    "技术标": [
        ("一、项目理解与技术响应", "理解业主需求，对招标文件作出全面技术响应"),
        ("二、总体技术方案", "阐述项目总体设计思路、技术路线和方案对比"),
        ("三、关键工程技术难点与对策", "识别项目关键技术难点，给出针对性解决方案"),
        ("四、设计组织与人员配置", "说明项目组织架构、核心团队、专业配置"),
        ("五、进度计划与保障措施", "编制项目进度计划，说明保障措施"),
        ("六、质量控制与验收标准", "说明质量控制体系、验收标准和保障"),
    ],
    "商务标": [
        ("一、投标函", "正式投标函，响应业主招标要求"),
        ("二、报价说明与商务条款", "详细报价构成、商务条款响应"),
        ("三、企业资质与业绩", "展示企业资质、类似项目业绩"),
        ("四、付款方式与履约保证金", "说明付款方式、履约保证金安排"),
        ("五、违约责任与争议解决", "明确违约责任、争议解决机制"),
    ],
    "资格预审": [
        ("一、申请人基本信息", "申请人基本情况、营业执照等"),
        ("二、企业资质与资信", "资质等级、资信证明"),
        ("三、类似项目业绩", "近三年类似项目业绩清单"),
        ("四、人员配置与设备", "关键人员、技术装备"),
        ("五、财务状况", "近三年财务报告"),
    ],
}


class OutlinePlanner:
    """阶段 1：生成标书大纲。"""

    def __init__(self) -> None:
        self.mcp = get_mcp_client()

    async def plan(
        self,
        project: Dict[str, Any],
        doc_type: str = "技术标",
        style: str = "标准",
        template_sections: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """生成大纲。

        返回 dict：
        {
            "doc_type": "技术标",
            "style": "标准",
            "style_baseline": "本标书采用...",
            "sections": [
                {"index": 1, "title": "...", "summary": "...", "target_words": 800},
                ...
            ],
            "fact_sheet": {...}
        }
        """
        # 1. 选骨架：模板 → 默认
        if template_sections:
            sections_raw = [(s, "") for s in template_sections]
        else:
            sections_raw = DEFAULT_SECTIONS.get(doc_type, DEFAULT_SECTIONS["技术标"])

        # 2. 用 LLM 精炼每章摘要 + 目标字数（如果 LLM 可用）
        sections: List[Dict[str, Any]] = []
        for i, (title, default_summary) in enumerate(sections_raw, 1):
            summary = default_summary or f"本章围绕「{title}」展开论述"
            target = self._estimate_target_words(i, len(sections_raw), project.get("estimated_amount"))
            sections.append({
                "index": i,
                "title": title,
                "summary": summary,
                "target_words": target,
            })

        # 3. 推断风格基线
        style_baseline = self._infer_style_baseline(style, project)

        # 4. 初始化 FactSheet
        fs = FactSheet(
            project_name=project.get("project_name", ""),
            client_name=project.get("client_name", ""),
            project_type=project.get("project_type", ""),
            estimated_amount=float(project.get("estimated_amount") or 0.0),
            bid_deadline=str(project.get("bid_deadline") or "") or None,
            structure_type=project.get("structure_type", ""),
            floor_count=int(project.get("floor_count") or 0),
            area_sqm=float(project.get("area_sqm") or 0.0),
            style_baseline=style_baseline,
        )
        # 从模板里抽人员（如果模板有提及）
        if template_sections:
            # 尝试从模板文本抽取（template_sections 是 list[str]）
            template_text = "\n".join(template_sections)
            for p in extract_personnel(template_text):
                fs.personnel.append(p)

        # 5. 让 LLM 重新润色一遍大纲摘要（如果可用）
        try:
            refined = await self._llm_refine_summaries(sections, project, doc_type, style)
            if refined:
                sections = refined
        except Exception as e:  # noqa: BLE001
            logger.debug("llm refine summaries skipped: %s", e)

        return {
            "doc_type": doc_type,
            "style": style,
            "style_baseline": style_baseline,
            "sections": sections,
            "fact_sheet": fs.to_dict(),
            "total_target_words": sum(s["target_words"] for s in sections),
        }

    @staticmethod
    def _estimate_target_words(index: int, total: int, amount: Optional[float]) -> int:
        """估算每章目标字数（基于章序 + 项目金额）。"""
        base = {1: 800, 2: 1500, 3: 1200, 4: 1000, 5: 800, 6: 700}.get(index, 600)
        if amount and amount > 5e8:  # 5 亿以上大项目
            base = int(base * 1.5)
        return base

    @staticmethod
    def _infer_style_baseline(style: str, project: Dict[str, Any]) -> str:
        """推断风格基线描述（注入 LLM prompt 用）。"""
        style_map = {
            "标准": "本标书采用标准、规范的表达风格。术语准确、逻辑清晰、论证充分、数据翔实。",
            "保守": "本标书采用稳妥、成熟的表达风格。强调成功案例、成熟工艺、风险可控。避免激进措辞。",
            "激进": "本标书采用突破、创新的表达风格。强调差异化竞争优势、行业领先地位、独特技术方案。",
            "创新型": "本标书采用首创、突破性的表达风格。强调独家技术、革命性方案、颠覆性创新。",
        }
        base = style_map.get(style, style_map["标准"])
        pt = project.get("project_type", "")
        if pt:
            base += f"项目类型为{pt}，需贴合{pt}项目的行业惯例与业主关注点。"
        return base

    async def _llm_refine_summaries(
        self,
        sections: List[Dict[str, Any]],
        project: Dict[str, Any],
        doc_type: str,
        style: str,
    ) -> Optional[List[Dict[str, Any]]]:
        """让 LLM 重新润色每章摘要（~200 字）。失败则返回 None，沿用默认。"""
        sections_md = "\n".join(
            f"{i+1}. {s['title']}（当前摘要：{s['summary']}）"
            for i, s in enumerate(sections)
        )
        prompt = (
            f"请基于以下项目信息，对「{doc_type}」每章的【200 字摘要】进行专业润色，使其更贴合{style}风格。\n"
            f"项目名：{project.get('project_name', '')}\n"
            f"客户：{project.get('client_name', '')}\n"
            f"类型：{project.get('project_type', '')}\n"
            f"结构：{project.get('structure_type', '')}\n\n"
            f"章节列表：\n{sections_md}\n\n"
            "请严格用如下 JSON 数组返回（不要其他内容）：\n"
            '[{"index": 1, "summary": "..."}, {"index": 2, "summary": "..."}, ...]'
        )
        system = "你是 DDW 标书撰写专家。仅返回 JSON，不要解释。"
        text = await self.mcp.llm_chat(prompt, system=system, temperature=0.3)
        return self._parse_llm_summaries(text, sections)

    @staticmethod
    def _parse_llm_summaries(text: str, fallback: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        """从 LLM 输出解析 JSON 摘要。"""
        # 尝试从 markdown code block 中提取
        m = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                by_idx = {d["index"]: d.get("summary", "") for d in data if "index" in d}
                for s in fallback:
                    if s["index"] in by_idx and by_idx[s["index"]]:
                        s["summary"] = by_idx[s["index"]]
                return fallback
            except (json.JSONDecodeError, KeyError, TypeError):
                pass
        return None


__all__ = ["DEFAULT_SECTIONS", "OutlinePlanner"]
