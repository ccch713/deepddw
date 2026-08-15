"""阶段 3：Consistency Checker（跨章一致性检查 + 局部重写）。

从所有章节内容里抽取事实 → 比对 FactSheet → 标记冲突 → 局部重写。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from plugins.ddw_bid_writer.services.fact_sheet import (
    FactSheet,
    extract_dates,
    extract_personnel,
)
from plugins.ddw_bid_writer.services.mcp_client import get_mcp_client

logger = logging.getLogger(__name__)


class ConsistencyChecker:
    """阶段 3：跨章一致性检查。"""

    def __init__(self) -> None:
        self.mcp = get_mcp_client()

    async def check(
        self,
        fact_sheet: FactSheet,
        sections: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """检查所有章节的一致性，返回冲突列表 + 修订建议。"""
        all_text = "\n\n".join(s.get("content", "") for s in sections)
        conflicts: List[Dict[str, Any]] = []

        # 1. 人员一致性
        conflicts.extend(self._check_personnel(fact_sheet, all_text))
        # 2. 金额一致性
        conflicts.extend(self._check_amount(fact_sheet, all_text))
        # 3. 日期一致性
        conflicts.extend(self._check_dates(fact_sheet, all_text))
        # 4. 结构类型一致性
        conflicts.extend(self._check_structure(fact_sheet, all_text))

        # 5. 章节内事实抽取 → 反馈到 FactSheet
        new_facts: List[str] = []
        for s in sections:
            updated = fact_sheet.update_from_section(s.get("content", ""), s.get("title", ""))
            new_facts.extend(updated)

        return {
            "conflict_count": len(conflicts),
            "conflicts": conflicts,
            "new_facts_extracted": new_facts,
            "fact_sheet": fact_sheet.to_dict(),
        }

    # ----------------- 检查项 ----------------- #

    @staticmethod
    def _check_personnel(fs: FactSheet, text: str) -> List[Dict[str, Any]]:
        """检查同一角色是否有不同的人名。"""
        out: List[Dict[str, Any]] = []
        for p in extract_personnel(text):
            # 与 fs 已有人员对比
            same_role = [x for x in fs.personnel if x.role == p.role]
            if same_role and not any(x.name == p.name for x in same_role):
                out.append({
                    "type": "personnel_mismatch",
                    "severity": "error",
                    "description": f"角色「{p.role}」在正文中出现 {p.name}，与 FactSheet 不一致（{', '.join(x.name for x in same_role)}）",
                    "expected": [x.name for x in same_role],
                    "actual": p.name,
                })
        return out

    @staticmethod
    def _check_amount(fs: FactSheet, text: str) -> List[Dict[str, Any]]:
        """检查金额数字一致性。"""
        out: List[Dict[str, Any]] = []
        if fs.estimated_amount <= 0:
            return out
        # 文本中所有类似金额的数
        money_re = re.findall(r"(\d[\d,，\.]*\d|\d)\s*亿元|(\d[\d,，\.]*\d|\d)\s*万元", text)
        # 简化：检测"X 亿"或"X 万"出现次数和上下文
        for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(亿|万)元", text):
            val = float(m.group(1))
            unit = m.group(2)
            actual = val * (1e8 if unit == "亿" else 1e4)
            # 容忍 10% 误差
            if abs(actual - fs.estimated_amount) / max(1, fs.estimated_amount) > 0.1:
                # 取上下文
                start = max(0, m.start() - 30)
                end = min(len(text), m.end() + 30)
                ctx = text[start:end].replace("\n", " ")
                out.append({
                    "type": "amount_mismatch",
                    "severity": "warn",
                    "description": f"正文出现 {val}{unit}元，FactSheet 估算金额为 {fs.estimated_amount:,.0f} 元（差异 > 10%）",
                    "context": ctx,
                    "expected": fs.estimated_amount,
                    "actual": actual,
                })
        return out

    @staticmethod
    def _check_dates(fs: FactSheet, text: str) -> List[Dict[str, Any]]:
        """检查日期一致性。"""
        out: List[Dict[str, Any]] = []
        if not fs.bid_deadline:
            return out
        expected = fs.bid_deadline[:10].replace("-", "")  # YYYYMMDD
        # 文本中所有类似日期
        for d in extract_dates(text):
            actual = d.value.replace("-", "").replace(".", "").replace("/", "").replace("年", "").replace("月", "").replace("日", "")[:8]
            # 简化比对：只比对"截止"相关的
            if "截止" in d.key or "截止" in text[max(0, text.find(d.value) - 20):text.find(d.value) + 20]:
                if actual and actual != expected:
                    out.append({
                        "type": "date_mismatch",
                        "severity": "error",
                        "description": f"正文出现截止日 {d.value}，FactSheet 投标截止为 {fs.bid_deadline[:10]}",
                        "expected": fs.bid_deadline[:10],
                        "actual": d.value,
                    })
        return out

    @staticmethod
    def _check_structure(fs: FactSheet, text: str) -> List[Dict[str, Any]]:
        """检查结构类型一致性。"""
        out: List[Dict[str, Any]] = []
        if not fs.structure_type:
            return out
        valid_types = {"框架", "框剪", "钢结构", "砖混", "剪力墙"}
        for t in valid_types:
            if t in text and t != fs.structure_type:
                out.append({
                    "type": "structure_mismatch",
                    "severity": "warn",
                    "description": f"正文提及结构类型「{t}」，FactSheet 为「{fs.structure_type}」",
                    "expected": fs.structure_type,
                    "actual": t,
                })
        return out

    # ----------------- 局部重写 ----------------- #

    async def fix_conflicts(
        self,
        fact_sheet: FactSheet,
        sections: List[Dict[str, Any]],
        conflicts: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """根据冲突列表，触发局部重写。"""
        # 简单实现：对每个含冲突的章节，让 LLM 基于 FactSheet 修正
        if not conflicts:
            return sections
        conflict_by_section: Dict[int, List[Dict[str, Any]]] = {}
        # 简化：把冲突归到所有章节（实际可根据冲突位置细化）
        for c in conflicts:
            for s in sections:
                # 简化匹配：描述里有关键字 = 该章有冲突
                if c.get("context") and c["context"][:30] in s.get("content", ""):
                    conflict_by_section.setdefault(s["index"], []).append(c)
                elif not c.get("context"):
                    conflict_by_section.setdefault(s["index"], []).append(c)

        fixed: List[Dict[str, Any]] = []
        for s in sections:
            cs = conflict_by_section.get(s["index"])
            if not cs:
                fixed.append(s)
                continue
            new_content = await self._fix_one(s, cs, fact_sheet)
            fixed.append({**s, "content": new_content, "fixed": True})
        return fixed

    async def _fix_one(
        self,
        section: Dict[str, Any],
        conflicts: List[Dict[str, Any]],
        fact_sheet: FactSheet,
    ) -> str:
        """单章修复：让 LLM 按 FactSheet 修正冲突。"""
        prompt = (
            f"你是一名标书校对专家。请基于 FactSheet 修正以下章节中的事实冲突，\n"
            f"保持原有结构、风格、字数不变，仅修改冲突处。\n\n"
            f"## FactSheet（事实基线）\n{fact_sheet.to_markdown()}\n\n"
            f"## 待修正章节：{section.get('title', '')}\n{section.get('content', '')}\n\n"
            f"## 冲突列表\n" + "\n".join(f"- {c['description']}" for c in conflicts) + "\n\n"
            "请直接输出修正后的完整章节内容（Markdown 格式）："
        )
        system = "你是 DDW 标书校对专家。保持原风格和结构，仅修事实冲突。"
        return await self.mcp.llm_chat(prompt, system=system, temperature=0.1, max_tokens=4000)


import re  # noqa: E402  (放在最后避免顶部 import 顺序问题)

__all__ = ["ConsistencyChecker"]
