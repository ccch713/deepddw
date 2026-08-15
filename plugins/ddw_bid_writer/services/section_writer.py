"""阶段 2：Section Writer（并行生成各章节，D RAG 增强）。

每章 prompt 注入 4 块：
1. FactSheet（硬约束）
2. 风格基线
3. 衔接上下文（前一章结尾 + 后一章摘要）
4. 章节具体要求
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from plugins.ddw_bid_writer.services.fact_sheet import FactSheet
from plugins.ddw_bid_writer.services.mcp_client import get_mcp_client
from plugins.ddw_bid_writer.services.vector_store import TenantKnowledgeStore

logger = logging.getLogger(__name__)


class SectionWriter:
    """阶段 2：并行章节生成（带 RAG 增强）。"""

    def __init__(self) -> None:
        self.mcp = get_mcp_client()

    async def write_all(
        self,
        project: Dict[str, Any],
        doc_type: str,
        style: str,
        sections: List[Dict[str, Any]],
        fact_sheet: FactSheet,
        tenant_id: int,
        rag_top_k: int = 3,
        prev_section_tail: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """并发生成所有章节。"""
        kb = TenantKnowledgeStore(tenant_id)
        # 准备衔接上下文
        nxt_summaries = [s.get("summary", "")[:150] for s in sections[1:]] + [""]
        # 并发生成
        tasks = [
            self._write_one(
                project=project,
                doc_type=doc_type,
                style=style,
                section=s,
                fact_sheet=fact_sheet,
                kb=kb,
                rag_top_k=rag_top_k,
                prev_tail=prev_section_tail if i == 0 else None,
                next_summary=nxt_summaries[i],
            )
            for i, s in enumerate(sections)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out: List[Dict[str, Any]] = []
        for s, r in zip(sections, results):
            if isinstance(r, Exception):
                logger.exception("section %s failed", s.get("title"))
                out.append({
                    "index": s["index"],
                    "title": s["title"],
                    "content": f"（本章生成失败：{r}）",
                    "error": str(r),
                    "rag_context": "",
                })
            else:
                out.append(r)
        return out

    async def _write_one(
        self,
        project: Dict[str, Any],
        doc_type: str,
        style: str,
        section: Dict[str, Any],
        fact_sheet: FactSheet,
        kb: TenantKnowledgeStore,
        rag_top_k: int,
        prev_tail: Optional[str],
        next_summary: Optional[str],
    ) -> Dict[str, Any]:
        """生成单章。"""
        # 1. RAG 检索相似章节
        rag_query = f"{doc_type} {section['title']} {project.get('project_type', '')}"
        try:
            hits = await kb.search(rag_query, top_k=rag_top_k)
        except Exception as e:  # noqa: BLE001
            logger.warning("RAG search failed: %s", e)
            hits = []
        rag_context = "\n\n---\n\n".join(
            f"【参考案例 {i+1}】（相似度 {h['score']:.2f}）\n{h['content'][:600]}"
            for i, h in enumerate(hits)
        ) if hits else "（无相似历史案例可参考）"

        # 2. 拼接 prompt
        prompt = self._build_prompt(
            project, doc_type, style, section, fact_sheet, rag_context, prev_tail, next_summary
        )
        system = self._build_system(style, doc_type, fact_sheet)

        # 3. LLM 生成
        content = await self.mcp.llm_chat(
            prompt, system=system, temperature=0.3, max_tokens=section.get("target_words", 1000) * 2
        )

        # 4. 后处理：保证 Markdown 标题层级
        content = self._ensure_heading(content, section["title"])

        return {
            "index": section["index"],
            "title": section["title"],
            "content": content,
            "rag_context": rag_context,
            "rag_hits": [
                {"score": h["score"], "doc_id": h["doc_id"], "file_name": h["metadata"].get("file_name", "")}
                for h in hits
            ],
        }

    @staticmethod
    def _build_prompt(
        project: Dict[str, Any],
        doc_type: str,
        style: str,
        section: Dict[str, Any],
        fact_sheet: FactSheet,
        rag_context: str,
        prev_tail: Optional[str],
        next_summary: Optional[str],
    ) -> str:
        parts: List[str] = []
        parts.append(f"# 任务：撰写「{section['title']}」章节")
        parts.append("")
        parts.append("## 项目基本信息")
        parts.append(f"- 项目名：{project.get('project_name', '')}")
        parts.append(f"- 客户：{project.get('client_name', '')}")
        parts.append(f"- 项目类型：{project.get('project_type', '')}")
        parts.append(f"- 结构类型：{project.get('structure_type', '')}")
        if project.get("estimated_amount"):
            parts.append(f"- 估算金额：{project['estimated_amount']:,.0f} 元")
        if project.get("area_sqm"):
            parts.append(f"- 面积：{project['area_sqm']:,.0f} ㎡")
        parts.append("")
        parts.append("## 章节要求")
        parts.append(f"- 章节标题：{section['title']}")
        parts.append(f"- 章节摘要：{section['summary']}")
        parts.append(f"- 目标字数：约 {section.get('target_words', 800)} 字")
        parts.append(f"- 文档类型：{doc_type}")
        parts.append(f"- 写作风格：{style}")
        parts.append("")
        parts.append("## 硬约束（必须严格遵循，不允许更改数值、日期、名称）")
        parts.append(fact_sheet.to_markdown())
        parts.append("")
        if prev_tail:
            parts.append("## 衔接上文（前章结尾，约 200 字）")
            parts.append(prev_tail[:600])
            parts.append("")
        if next_summary:
            parts.append("## 衔接下文（后章摘要）")
            parts.append(next_summary[:300])
            parts.append("")
        parts.append("## 历史标书参考案例（RAG 检索）")
        parts.append(rag_context)
        parts.append("")
        parts.append("## 输出要求")
        parts.append("- 直接输出本章内容，不要解释、不要 JSON 包装")
        parts.append("- 标题用 ## 级别（一级标题留给标书主标题）")
        parts.append("- 段落清晰，必要时用 bullet 列点")
        parts.append("- 数据 / 名称 / 日期必须与 FactSheet 一致")
        parts.append("")
        parts.append("请开始撰写：")
        return "\n".join(parts)

    @staticmethod
    def _build_system(style: str, doc_type: str, fact_sheet: FactSheet) -> str:
        return (
            f"你是 DDW 设计院标书撰写专家，正在协助撰写「{doc_type}」。\n"
            f"本次写作风格：{style}。\n"
            f"\n"
            f"## 风格基线\n{fact_sheet.style_baseline or '标准风格'}\n"
            f"\n"
            f"## 关键规则\n"
            f"1. 所有数据、日期、人员名必须与 FactSheet 一致，不允许编造\n"
            f"2. 突出企业技术实力、类似业绩、方案优势\n"
            f"3. 避免空话套话，每段必须有具体内容\n"
            f"4. 用专业术语，避免口语化\n"
        )

    @staticmethod
    def _ensure_heading(content: str, expected_title: str) -> str:
        """保证章节内容以二级标题 ## 开头。"""
        if not content.strip():
            return f"## {expected_title}\n\n（生成失败）\n"
        # 如果第一行不是 ## 开头，补一个
        first_line = content.strip().split("\n", 1)[0].strip()
        if not first_line.startswith("#"):
            return f"## {expected_title}\n\n{content.strip()}\n"
        return content.strip() + "\n"


__all__ = ["SectionWriter"]
