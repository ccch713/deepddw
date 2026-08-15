"""蒸馏结果 → 记忆引擎导出。"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

EXPORT_PROMPT = """以下是一个知识蒸馏方法论单元，请为其生成适合存入企业记忆引擎的摘要。

标题：{title}
类型：{unit_type}
R 段（原始知识）：{r_section}
A1 段（应用）：{a1_section}

输出 JSON（不超过 200 字）：
{{
  "summary": "50字摘要",
  "memory_content": "完整记忆内容（独立可理解，200字以内）",
  "tags": ["标签1", "标签2"]
}}
"""


async def export_distill_to_memory(
    units: list[dict],
    target_layer: str = "department",
    department_id: int | None = None,
    position_id: int | None = None,
    llm_chat_fn: Callable | None = None,
    create_memory_fn: Callable | None = None,
    filter_min_quality: float = 60.0,
) -> dict:
    """把蒸馏结果导出到记忆引擎。

    units: list of dict with keys: title, unit_type, r_section, a1_section, quality_score, id
    llm_chat_fn: async (system, user) -> str
    create_memory_fn: async (tenant_id, layer, content, creator_id, tags, source_type) -> dict

    返回: {"exported": int, "skipped": int, "memory_ids": list[int]}
    """
    if not create_memory_fn:
        logger.warning("create_memory_fn not provided, skipping export")
        return {"exported": 0, "skipped": len(units), "memory_ids": []}

    exported = 0
    skipped = 0
    memory_ids = []

    for unit in units:
        quality = unit.get("quality_score", 0)
        if quality and quality < filter_min_quality:
            skipped += 1
            continue

        # 生成记忆内容
        title = unit.get("title", "")
        unit_type = unit.get("unit_type", "framework")
        r_section = unit.get("r_section", "")[:500]
        a1_section = unit.get("a1_section", "")[:500]

        memory_content = f"[{unit_type}] {title}"
        summary = title
        tags = ["distill", unit_type]

        if llm_chat_fn and r_section:
            try:
                raw = await llm_chat_fn(
                    "你是企业知识摘要助手。",
                    EXPORT_PROMPT.format(
                        title=title, unit_type=unit_type,
                        r_section=r_section, a1_section=a1_section,
                    ),
                )
                if "```json" in raw:
                    raw = raw.split("```json")[1].split("```")[0]
                parsed = json.loads(raw.strip())
                memory_content = parsed.get("memory_content", memory_content)
                summary = parsed.get("summary", summary)
                tags = parsed.get("tags", tags) + ["distill"]
            except Exception as e:
                logger.warning("memory export LLM failed for unit %s: %s", unit.get("id"), e)

        try:
            result = await create_memory_fn(
                layer=target_layer,
                content=memory_content,
                summary=summary,
                tags=tags,
                source_type="distill",
                department_id=department_id,
                position_id=position_id,
            )
            if result and "id" in result:
                memory_ids.append(result["id"])
            exported += 1
        except Exception as e:
            logger.warning("memory export failed for unit %s: %s", unit.get("id"), e)
            skipped += 1

    return {"exported": exported, "skipped": skipped, "memory_ids": memory_ids}


__all__ = ["export_distill_to_memory"]
