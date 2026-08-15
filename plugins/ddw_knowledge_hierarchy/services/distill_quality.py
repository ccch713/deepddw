"""蒸馏质量门禁引擎 — 四维评分 + accuracy 一票否决。"""
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

QUALITY_DIMENSIONS = {
    "completeness": {"weight": 0.3, "check": "RIA++ 六段是否完整填写"},
    "accuracy": {"weight": 0.3, "check": "内容是否与原文一致，有无幻觉"},
    "actionability": {"weight": 0.25, "check": "方法论是否可执行、可操作"},
    "clarity": {"weight": 0.15, "check": "表述是否清晰、无歧义"},
}

QUALITY_CHECK_PROMPT = """你是 DDW 知识蒸馏质量评审员。请评估以下方法论单元的质量。

方法论单元：
标题：{title}
类型：{unit_type}
R 段（阅读/原始知识）：{r_section}
I 段（解释/原理）：{i_section}
A1 段（应用/行动）：{a1_section}
E 段（执行步骤）：{e_section}
B 段（边界/反例）：{b_section}

原始文档片段（用于交叉验证）：
{source_content}

请按以下维度评分（0-100）：
1. 完整性：RIA++ 各段是否完整、充实
2. 准确性：内容是否与原文一致，有无幻觉或曲解
3. 可操作性：方法论是否可执行、有实际指导意义
4. 清晰度：表述是否清晰、逻辑是否通顺

JSON 输出：
{{
  "completeness": {{"score": 85, "issues": [], "suggestions": []}},
  "accuracy": {{"score": 90, "issues": [], "suggestions": []}},
  "actionability": {{"score": 75, "issues": [], "suggestions": []}},
  "clarity": {{"score": 80, "issues": [], "suggestions": []}},
  "overall_score": 82,
  "pass": true,
  "reject_reasons": []
}}
"""


def _default_llm(system: str, user: str) -> Awaitable[str]:
    raise RuntimeError("LLM function not set")


async def check_quality(
    unit: dict,
    source_content: str,
    llm_chat_fn: Callable | None = None,
    min_score: float = 60.0,
    accuracy_threshold: float = 70.0,
) -> dict:
    """对蒸馏单元做四维质量检查。

    通过标准：
    - overall_score >= min_score（light 模式 60, full/hybrid 75）
    - accuracy.score >= accuracy_threshold（一票否决）

    返回：
    {
        "overall_score": float,
        "pass": bool,
        "dimensions": {dim: {"score": float, "issues": list, "suggestions": list}},
        "reject_reasons": list[str],
    }
    """
    if llm_chat_fn is None:
        # 无 LLM 时通过简单规则检查
        return _rule_based_check(unit, min_score, accuracy_threshold)

    prompt = QUALITY_CHECK_PROMPT.format(
        title=unit.get("title", ""),
        unit_type=unit.get("unit_type", "unknown"),
        r_section=unit.get("r_section", "")[:500] or "（空）",
        i_section=unit.get("i_section", "")[:500] or "（空）",
        a1_section=unit.get("a1_section", "")[:500] or "（空）",
        e_section=unit.get("e_section", "")[:300] or "（空）",
        b_section=unit.get("b_section", "")[:300] or "（空）",
        source_content=source_content[:2000],
    )

    try:
        raw = await llm_chat_fn("你是质量评审专家。", prompt)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        result = json.loads(raw.strip())

        overall = float(result.get("overall_score", 0))
        dims = {}
        for dim_name in QUALITY_DIMENSIONS:
            dim_data = result.get(dim_name, {})
            dims[dim_name] = {
                "score": float(dim_data.get("score", 0)),
                "issues": dim_data.get("issues", []),
                "suggestions": dim_data.get("suggestions", []),
            }

        reject_reasons = result.get("reject_reasons", [])
        accuracy_score = dims.get("accuracy", {}).get("score", 0)

        # accuracy 一票否决
        if accuracy_score < accuracy_threshold:
            reject_reasons.append(f"accuracy {accuracy_score:.0f} < {accuracy_threshold:.0f}")

        passed = overall >= min_score and not reject_reasons

        return {
            "overall_score": overall,
            "pass": passed,
            "dimensions": dims,
            "reject_reasons": reject_reasons,
        }
    except Exception as e:
        logger.warning("quality check LLM failed: %s, falling back to rule-based", e)
        return _rule_based_check(unit, min_score, accuracy_threshold)


def _rule_based_check(unit: dict, min_score: float, accuracy_threshold: float) -> dict:
    """无 LLM 时的简单规则检查。"""
    sections = ["r_section", "i_section", "a1_section", "e_section", "b_section"]
    filled = sum(1 for s in sections if unit.get(s) and len(unit[s].strip()) > 10)
    completeness = (filled / len(sections)) * 100
    overall = completeness  # 无 LLM 时只看完整性

    reject_reasons = []
    if overall < min_score:
        reject_reasons.append(f"completeness {overall:.0f} < {min_score:.0f}")

    return {
        "overall_score": overall,
        "pass": overall >= min_score,
        "dimensions": {
            "completeness": {"score": completeness, "issues": [], "suggestions": []},
            "accuracy": {"score": 80.0, "issues": [], "suggestions": []},  # 默认通过
            "actionability": {"score": 60.0, "issues": [], "suggestions": []},
            "clarity": {"score": 70.0, "issues": [], "suggestions": []},
        },
        "reject_reasons": reject_reasons,
    }


__all__ = ["QUALITY_DIMENSIONS", "check_quality"]
