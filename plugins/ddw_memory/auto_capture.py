"""ddw_memory 自动记忆捕获 — 对话摘要 + 知识提取。"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

SUMMARY_SYSTEM = """你是 DDW 企业记忆引擎的知识提取助手。
从企业用户对话中提取有价值的知识要点。

规则：
1. 只提取工作相关知识（流程、经验、决策、问题解决方案）
2. 忽略闲聊、寒暄、重复内容
3. 质量/安全/合规相关知识优先提取
4. 不提取个人隐私信息
5. 知识要点必须完整、可独立理解
"""

SUMMARY_USER = """对话内容：
{conversation}

请 JSON 输出：
{{
  "summary": "50字以内摘要",
  "knowledge_points": ["要点1", "要点2"],
  "suggested_layer": "personal|position|department|enterprise",
  "suggested_tags": ["标签1", "标签2"],
  "confidence": 0.0-1.0
}}
"""


async def summarize_conversation(
    messages: list[dict],
    llm_chat_fn,
) -> dict:
    """调 LLM 生成对话摘要。返回 parsed JSON。

    llm_chat_fn: async (system: str, user: str) -> str
    """
    conversation = "\n".join(
        f"[{m.get('role', 'user')}] {m.get('content', '')}" for m in messages
    )
    if len(conversation) > 8000:
        conversation = conversation[:8000] + "\n...(截断)"

    try:
        raw = await llm_chat_fn(SUMMARY_SYSTEM, SUMMARY_USER.format(conversation=conversation))
        # 尝试从 raw 中提取 JSON
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        result = json.loads(raw.strip())
        return {
            "summary": result.get("summary", ""),
            "knowledge_points": result.get("knowledge_points", []),
            "suggested_layer": result.get("suggested_layer", "personal"),
            "suggested_tags": result.get("suggested_tags", []),
            "confidence": float(result.get("confidence", 0.5)),
        }
    except Exception as e:
        logger.warning("conversation summarization failed: %s", e)
        return {
            "summary": "",
            "knowledge_points": [],
            "suggested_layer": "personal",
            "suggested_tags": [],
            "confidence": 0.0,
        }


async def maybe_capture_session(
    tenant_id: int,
    user_id: int,
    session_id: str,
    messages: list[dict],
    config: dict,
    llm_chat_fn,
    create_pending_fn,
) -> dict | None:
    """对话达到 N 轮后自动摘要捕获。

    config: {"enabled": bool, "capture_after_turns": int, "exclude_patterns": list[str]}
    llm_chat_fn: async (system, user) -> str
    create_pending_fn: async (tenant_id, user_id, session_id, summary, ...) -> dict
    """
    if not config.get("enabled", True):
        return None

    # 对话轮次检查（每 2 条消息 = 1 轮）
    turns = len(messages) // 2
    if turns < config.get("capture_after_turns", 5):
        return None

    # 排除模式检查
    exclude = config.get("exclude_patterns", [])
    full_text = " ".join(m.get("content", "") for m in messages)
    for pattern in exclude:
        if pattern and pattern in full_text:
            logger.info("capture skipped: exclude pattern '%s' matched", pattern)
            return None

    # LLM 摘要
    result = await summarize_conversation(messages, llm_chat_fn)
    if not result["summary"] or result["confidence"] < 0.3:
        return None

    # 创建待审核捕获
    return await create_pending_fn(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        summary=result["summary"],
        knowledge_points=result["knowledge_points"],
        suggested_layer=result["suggested_layer"],
        suggested_tags=result["suggested_tags"],
        confidence=result["confidence"],
    )


__all__ = ["maybe_capture_session", "summarize_conversation"]
