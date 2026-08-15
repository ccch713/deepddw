"""阶段 4：Polisher（全文润色 + 统稿）。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from plugins.ddw_bid_writer.services.fact_sheet import FactSheet
from plugins.ddw_bid_writer.services.mcp_client import get_mcp_client

logger = logging.getLogger(__name__)


class Polisher:
    """阶段 4：全文润色。"""

    def __init__(self) -> None:
        self.mcp = get_mcp_client()

    async def polish(
        self,
        project: Dict[str, Any],
        doc_type: str,
        style: str,
        sections: List[Dict[str, Any]],
        fact_sheet: FactSheet,
    ) -> Dict[str, Any]:
        """全文润色。

        行为：
        1. 先把 sections 拼成完整草稿
        2. 让 LLM 做整体润色（修辞统一、过渡自然、消除重复）
        3. 返回润色结果 + 润色前后的对比摘要
        """
        # 1. 拼装
        draft = self._assemble(sections, project, doc_type)
        if not draft.strip():
            return {"content": draft, "diff_summary": "草稿为空，跳过润色"}

        # 2. LLM 润色（如果可用）
        try:
            refined = await self._llm_polish(draft, project, doc_type, style, fact_sheet)
            if refined and refined.strip():
                return {
                    "content": refined,
                    "diff_summary": self._diff_summary(draft, refined),
                    "polished": True,
                }
        except Exception as e:  # noqa: BLE001
            logger.warning("llm polish failed: %s", e)

        return {"content": draft, "diff_summary": "未润色（LLM 不可用）", "polished": False}

    @staticmethod
    def _assemble(sections: List[Dict[str, Any]], project: Dict[str, Any], doc_type: str) -> str:
        """把 sections 拼成完整 Markdown 文档。"""
        parts: List[str] = []
        # 主标题
        title = f"# {project.get('project_name', '未命名项目')} — {doc_type}"
        parts.append(title)
        parts.append("")
        # 头部信息
        parts.append("> 投标方：" + (project.get("client_name") or "—"))
        parts.append("> 项目类型：" + (project.get("project_type") or "—"))
        if project.get("estimated_amount"):
            parts.append("> 估算金额：" + f"{project['estimated_amount']:,.0f} 元")
        if project.get("bid_deadline"):
            parts.append("> 投标截止：" + str(project["bid_deadline"])[:16])
        parts.append("")
        parts.append("---")
        parts.append("")
        # 章节
        for s in sections:
            content = s.get("content", "").strip()
            if content:
                parts.append(content)
                parts.append("")
        # 页脚
        parts.append("---")
        parts.append("")
        parts.append("_本标书由 DDW AI Hub 多 Agent 协作生成_")
        return "\n".join(parts)

    async def _llm_polish(
        self,
        draft: str,
        project: Dict[str, Any],
        doc_type: str,
        style: str,
        fact_sheet: FactSheet,
    ) -> str:
        """LLM 整体润色。"""
        # 截断：超长草稿分块润色（避免超 LLM 上下文）
        # 简单实现：直接全文交给 LLM，限制输入不超过 8000 字
        if len(draft) > 8000:
            # 分块润色（这里简化：只润色前 8000 字 + 警告）
            truncated = draft[:8000] + "\n\n...（后续章节略，请分章节分别润色）"
        else:
            truncated = draft
        prompt = (
            f"你是 DDW 标书润色专家。请对以下「{doc_type}」草稿做整体润色，\n"
            f"要求：\n"
            f"1. 保持 Markdown 标题层级\n"
            f"2. 修辞统一、过渡自然\n"
            f"3. 消除重复表述\n"
            f"4. 严格保留所有事实（数据/日期/名称）\n"
            f"5. 风格：{style}\n\n"
            f"## 草稿\n{truncated}"
        )
        system = (
            f"你是 DDW 标书润色专家。\n"
            f"风格基线：{fact_sheet.style_baseline or '标准风格'}"
        )
        return await self.mcp.llm_chat(prompt, system=system, temperature=0.4, max_tokens=8000)

    @staticmethod
    def _diff_summary(old: str, new: str) -> str:
        """对比润色前后变化（粗略统计）。"""
        return (
            f"润色前 {len(old)} 字 → 润色后 {len(new)} 字；"
            f"变化 {abs(len(new) - len(old))} 字（{(len(new) - len(old)) / max(1, len(old)) * 100:.1f}%）"
        )


__all__ = ["Polisher"]
