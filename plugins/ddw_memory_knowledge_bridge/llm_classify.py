"""LLM 知识分类 + 归档决策。"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

CLASSIFY_SYSTEM = """你是 DDW 知识管理系统的自动分类器。
根据记忆/文档内容，判断它应该归入哪个知识桶。

规则：
1. 优先匹配内容主题
2. 质量/安全/合规类归入质量知识桶
3. 行业法规/标准归入法规知识桶
4. 业务流程/SOP 归入流程知识桶
5. 如果没有匹配的知识桶，建议创建新桶
"""

CLASSIFY_USER = """内容：{content}
标签：{tags}
层级：{layer}
可选知识桶：{buckets}

JSON 输出：
{{
  "bucket": "桶名",
  "tags": ["标签1", "标签2"],
  "confidence": 0.0-1.0,
  "reasoning": "分类理由"
}}
"""

DOC_SUMMARY_SYSTEM = """你是 DDW 知识库摘要助手。
为知识库文档生成简洁摘要，用于导入记忆引擎。

规则：
1. 摘要不超过 200 字
2. 提取 3-5 个关键要点
3. 标注适用的岗位/部门
4. 如果涉及红线/强制规定，明确标出
"""

DOC_SUMMARY_USER = """文档标题：{title}
文档内容（前 3000 字）：{content}

JSON 输出：
{{
  "summary": "200字以内摘要",
  "key_points": ["要点1", "要点2"],
  "applicable_positions": ["岗位1", "岗位2"],
  "has_redlines": true,
  "suggested_tags": ["标签1", "标签2"]
}}
"""


async def classify_content(
    content: str,
    tags: list[str],
    layer: str,
    available_buckets: list[str],
    llm_chat_fn,
) -> dict:
    """用 LLM 对内容进行知识桶分类。"""
    try:
        prompt = CLASSIFY_USER.format(
            content=content[:2000],
            tags=", ".join(tags),
            layer=layer,
            buckets=", ".join(available_buckets) if available_buckets else "（无可用桶）",
        )
        raw = await llm_chat_fn(CLASSIFY_SYSTEM, prompt)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        result = json.loads(raw.strip())
        return {
            "suggested_bucket": result.get("bucket", ""),
            "suggested_tags": result.get("tags", []),
            "confidence": float(result.get("confidence", 0.5)),
            "reasoning": result.get("reasoning", ""),
        }
    except Exception as e:
        logger.warning("classify failed: %s", e)
        return {
            "suggested_bucket": "",
            "suggested_tags": tags,
            "confidence": 0.0,
            "reasoning": f"classify error: {e}",
        }


async def summarize_document(
    title: str,
    content: str,
    llm_chat_fn,
) -> dict:
    """用 LLM 为知识库文档生成摘要。"""
    try:
        prompt = DOC_SUMMARY_USER.format(title=title, content=content[:3000])
        raw = await llm_chat_fn(DOC_SUMMARY_SYSTEM, prompt)
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        result = json.loads(raw.strip())
        return {
            "summary": result.get("summary", "")[:200],
            "key_points": result.get("key_points", []),
            "applicable_positions": result.get("applicable_positions", []),
            "has_redlines": result.get("has_redlines", False),
            "suggested_tags": result.get("suggested_tags", []),
        }
    except Exception as e:
        logger.warning("summarize failed: %s", e)
        return {
            "summary": content[:200],
            "key_points": [],
            "applicable_positions": [],
            "has_redlines": False,
            "suggested_tags": [],
        }


__all__ = ["classify_content", "summarize_document"]
