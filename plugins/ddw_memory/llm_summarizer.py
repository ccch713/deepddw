"""ddw_memory LLM 摘要 + 知识蒸馏封装。"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

# LLM chat 函数类型：async (system: str, user: str) -> str
LLMChatFn = Callable[[str, str], Awaitable[str]]

POSITION_QUERY_SYSTEM = """你是 DDW 企业 AI 助手，正在回答关于岗位工作的提问。

岗位：{position_name}
SOP 标准流程：
{sop_steps}

相关岗位知识：
{position_memories}

企业制度红线：
{enterprise_redlines}

回答规则：
1. 优先遵循 SOP 流程
2. 涉及企业红线时必须明确标出 ⚠️
3. SOP 未覆盖的问题，基于岗位知识给出建议
4. 标注信息来源：[SOP] / [岗位知识] / [AI建议]
5. 如果信息不足，明确告知并建议咨询主管
"""


async def generate_position_answer(
    position_name: str,
    sop_steps: list[str],
    position_memories: list[str],
    enterprise_redlines: list[str],
    question: str,
    llm_chat_fn: LLMChatFn,
) -> str:
    """为岗位知识查询生成 LLM 回答。"""
    sop_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(sop_steps)) if sop_steps else "  （无 SOP 模板）"
    pos_text = "\n".join(f"  - {m}" for m in position_memories) if position_memories else "  （无岗位知识）"
    red_text = "\n".join(f"  ⚠️ {r}" for r in enterprise_redlines) if enterprise_redlines else "  （无红线）"

    system = POSITION_QUERY_SYSTEM.format(
        position_name=position_name,
        sop_steps=sop_text,
        position_memories=pos_text,
        enterprise_redlines=red_text,
    )
    try:
        return await llm_chat_fn(system, question)
    except Exception as e:
        logger.warning("position answer generation failed: %s", e)
        return f"（AI 回答生成失败：{e}）"


async def summarize_for_memory(
    content: str,
    llm_chat_fn: LLMChatFn,
) -> dict:
    """为记忆条目生成摘要。"""
    system = "你是企业知识摘要助手。请用不超过 50 字概括以下内容的核心要点。"
    try:
        raw = await llm_chat_fn(system, content[:2000])
        return {"summary": raw.strip()[:200]}
    except Exception as e:
        logger.warning("memory summarization failed: %s", e)
        return {"summary": content[:100]}


__all__ = ["LLMChatFn", "generate_position_answer", "summarize_for_memory"]
