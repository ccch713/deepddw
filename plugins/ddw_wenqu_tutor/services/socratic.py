"""苏格拉底对话引擎（prompt 组装 + 流式）。"""
from __future__ import annotations

from typing import Optional

from plugins.ddw_wenqu_tutor.prompt.chem_modes import (
    build_mode_card_prompt,
)
from plugins.ddw_wenqu_tutor.prompt.chemistry_safety import (
    SAFETY_IRON_RULES,
)
from plugins.ddw_wenqu_tutor.prompt.format_rules import (
    FORMAT_RULES,
)
from plugins.ddw_wenqu_tutor.prompt.physics_coach import (
    PHYSICS_COACH,
)
from plugins.ddw_wenqu_tutor.prompt.socratic_rules import (
    SOCRATIC_RULES,
)
from plugins.ddw_wenqu_tutor.prompt.token_budget import (
    estimate_tokens,
    truncate_to_budget,
)

# 角色映射（科目注册表唯一事实源，见 prompt/subject_meta.py）
from plugins.ddw_wenqu_tutor.prompt.subject_meta import SUBJECTS  # noqa: E402

COACH_ROLE: dict[str, str] = {
    sid: meta["coach"] for sid, meta in SUBJECTS.items()
}

# 章节上下文模板
CHAPTER_CONTEXT: str = "当前章节：{chapter}"

# 教材内容模板
TEXTBOOK_SECTION: str = "教材内容：{content}"

# 学习者画像模板
LEARNER_PROFILE: str = "学习者画像：{profile}"

# 防注入：用户输入处理
INJECTION_CHARS = ["## ", "### ", "#### ", "<system>", "</system>"]

# 阶段-规则映射：7 段动态裁剪
PHASE_RULE_MAP: dict[str, list[int]] = {
    "info_check":       [1, 2, 3, 4, 5, 6, 7],  # 默认全部注入（兼容旧调用）
    "mode_select":      [1, 2, 3],    # 裁剪：规则+角色+格式
    "chem_analysis":    [1, 2, 3, 4], # +安全铁律
    "answer_diag":      [1, 2, 3, 4, 5],  # +模式卡片
    "pinpoint":         [1, 2, 3, 4, 5, 6],  # +章节上下文
    "min_intervention": [1, 2, 3, 4, 5, 6, 7],  # +教材内容
    "verify_transfer":  [1, 2, 3, 4, 5, 6, 7],  # 同上
    "record":           [1, 2, 3, 4, 5, 6, 7],  # 同上
}

# 段编号对应：
# 1=socratic_rules  2=coach_role  3=format_rules
# 4=safety_rules  5=mode_card  6=chapter_context
# 7=textbook+learner_profile


def sanitize_user_input(content: str) -> str:
    """防注入：剥离标题 + XML 标签包围。"""
    # 剥离潜在注入标题
    for char in INJECTION_CHARS:
        content = content.replace(char, "")
    # XML 标签包围
    return f"<user-content>{content}</user-content>"


def build_system_prompt(
    subject: str,
    chapter: Optional[str] = None,
    textbook_chunk: Optional[str] = None,
    learner_profile: Optional[str] = None,
    max_tokens: int = 6000,
    # --- 新增参数 ---
    phase: str = "info_check",
    mode: Optional[str] = None,
    mastery_steps: Optional[list[str]] = None,
) -> str:
    """7 段 prompt 动态裁剪组装。

    段1：苏格拉底规则（含第 7 条化学特化 + STEP_MODE + 三级提示）
    段2：祁衡 or 林若薇（含四核心视角铁律）
    段3：旁白/正文/下课/语言格式规则
    段4：实验安全铁律（仅 chemistry subject）
    段5：模式卡片（仅当 mode 非空时注入）
    段6：章节上下文
    段7：教材内容 + 学习者画像
    """
    # 动态裁剪：根据 phase 决定注入哪些段
    rule_indices = PHASE_RULE_MAP.get(phase, [1, 2])

    sections = []

    # 段1：苏格拉底规则
    if 1 in rule_indices:
        sections.append(SOCRATIC_RULES)

    # 段2：教练角色
    if 2 in rule_indices:
        sections.append(
            COACH_ROLE.get(subject, PHYSICS_COACH)
        )

    # 段3：格式规则
    if 3 in rule_indices:
        sections.append(FORMAT_RULES)

    # 段4：安全铁律（仅化学）
    if 4 in rule_indices and subject == "chemistry":
        sections.append(SAFETY_IRON_RULES)

    # 段5：模式卡片（仅当 mode 非空）
    if 5 in rule_indices and mode:
        card_text = build_mode_card_prompt(mode)
        if card_text:
            sections.append(card_text)

    # 段6：章节上下文
    if 6 in rule_indices:
        sections.append(
            CHAPTER_CONTEXT.format(
                chapter=chapter or "总复习"
            )
        )

    # 段7：教材 + 学习者画像
    if 7 in rule_indices:
        sections.append(
            TEXTBOOK_SECTION.format(
                content=textbook_chunk
                or "（未导入教材，基于通用知识）"
            )
        )
        sections.append(
            LEARNER_PROFILE.format(
                profile=learner_profile
                or "（新学生，未知画像）"
            )
        )

    # 拼接
    prompt = "\n\n---\n\n".join(sections)

    # 截断到预算
    if estimate_tokens(prompt) > max_tokens:
        prompt = truncate_to_budget(prompt, max_tokens)

    return prompt


def build_user_message(
    content: str,
    history: Optional[list[dict]] = None,
) -> str:
    """构建用户消息（防注入处理）。"""
    sanitized = sanitize_user_input(content)

    if not history:
        return sanitized

    # 构建对话历史
    history_text = ""
    for msg in history[-6:]:  # 最近 6 轮
        role = msg.get("role", "user")
        text = msg.get("content", "")
        history_text += f"[{role}]: {text}\n"

    return f"对话历史：\n{history_text}\n当前问题：{sanitized}"


async def generate_socratic_reply(
    llm_client,
    system_prompt: str,
    user_message: str,
    model: str = "MiniMax-M3",
) -> str:
    """调用 LLM 生成苏格拉底回复。"""
    # 调 LLM Gateway
    response = await llm_client.generate(
        model=model,
        system=system_prompt,
        user=user_message,
        temperature=0.7,
        max_tokens=2000,
    )

    # 确保以提问结尾
    reply = response.strip()
    if not reply.endswith("？") and not reply.endswith("?"):
        reply += "？"

    return reply


__all__ = [
    "build_system_prompt",
    "build_user_message",
    "generate_socratic_reply",
    "sanitize_user_input",
    "PHASE_RULE_MAP",
]
