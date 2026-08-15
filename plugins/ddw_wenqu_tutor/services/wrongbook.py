"""错题本 + 微 Socratic 复盘生成。"""
from __future__ import annotations

import time
import uuid
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wenqu_tutor.models import (
    WenquWrongAnswer,
)


async def list_wrong_answers(
    db: AsyncSession,
    student_name: str = "CXY",
    resolved: Optional[bool] = None,
    limit: int = 50,
) -> list[WenquWrongAnswer]:
    """查询错题列表。"""
    query = select(WenquWrongAnswer).where(
        WenquWrongAnswer.student_name == student_name
    )

    if resolved is not None:
        query = query.where(
            WenquWrongAnswer.resolved == resolved
        )

    query = query.order_by(
        WenquWrongAnswer.created_at.desc()
    ).limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_wrong_answer(
    db: AsyncSession, wrong_id: str
) -> Optional[WenquWrongAnswer]:
    """获取单个错题。"""
    result = await db.execute(
        select(WenquWrongAnswer).where(
            WenquWrongAnswer.id == wrong_id
        )
    )
    return result.scalar_one_or_none()


async def mark_resolved(
    db: AsyncSession, wrong_id: str
) -> bool:
    """标记错题已解决。"""
    await db.execute(
        update(WenquWrongAnswer)
        .where(WenquWrongAnswer.id == wrong_id)
        .values(resolved=True)
    )
    await db.commit()
    return True


async def get_four_questions(
    db: AsyncSession, wrong_id: str,
) -> Optional[dict]:
    """获取错题四问详情。"""
    wrong = await get_wrong_answer(db, wrong_id)
    if not wrong:
        return None
    return {
        "wrong_id": wrong.id,
        "question_id": wrong.question_id,
        "student_answer": wrong.student_answer,
        "error_type": wrong.error_type,
        "mode": wrong.mode,
        "four_questions": {
            "correct_parts": wrong.correct_parts or "",
            "error_location": wrong.error_location or "",
            "error_root_cause": wrong.error_root_cause or "",
            "check_strategy": wrong.check_strategy or "",
        },
    }


def build_redo_prompt(wrong: WenquWrongAnswer) -> str:
    """错题触发 3-5 轮微 Socratic Loop（含四问卡片）。"""
    four_q_text = ""
    if wrong.correct_parts:
        four_q_text = f"""
【错题四问卡片】
做对了什么：{wrong.correct_parts}
错在哪儿：{wrong.error_location}
为什么错：{wrong.error_root_cause}
下次怎么检查：{wrong.check_strategy}
"""

    return (
        f"学生刚才做错了这道题"
        f"（{wrong.question_id}）：\n"
        f"学生答案：{wrong.student_answer}\n"
        f"错误类型：{wrong.error_type}\n"
        f"知识缺口：{wrong.knowledge_gap}\n"
        f"{four_q_text}\n"
        "现在开始苏格拉底复盘：\n"
        "1. 先展示四问卡片，让学生对照自查\n"
        "2. 第一问必须是引导学生重新审题（不提示答案）\n"
        "3. 之后每轮基于上一轮回答继续追问\n"
        "4. 直到学生自己说出正确思路（3-5 轮内）\n"
        "5. 最后让学生完整重做一遍"
    )


async def start_redo_session(
    db: AsyncSession, wrong_id: str,
) -> dict:
    """开始错题复盘会话（含四问卡片）。"""
    wrong = await get_wrong_answer(db, wrong_id)
    if not wrong:
        raise ValueError(f"Wrong answer {wrong_id} not found")

    redo_prompt = build_redo_prompt(wrong)

    session_id = f"WS_REDO_{int(time.time())}_{uuid.uuid4().hex[:6]}"

    first_question = "让我们重新看看这道题。\n"
    if wrong.correct_parts:
        first_question += (
            f"你做对了：{wrong.correct_parts}\n"
            f"但错在：{wrong.error_location}\n\n"
        )
    first_question += "你能告诉我，题目问的是什么吗？"

    four_questions = None
    if wrong.correct_parts:
        four_questions = {
            "correct_parts": wrong.correct_parts or "",
            "error_location": wrong.error_location or "",
            "error_root_cause": wrong.error_root_cause or "",
            "check_strategy": wrong.check_strategy or "",
        }

    return {
        "session_id": session_id,
        "first_question": first_question,
        "redo_prompt": redo_prompt,
        "four_questions": four_questions,
    }


__all__ = [
    "build_redo_prompt",
    "get_four_questions",
    "get_wrong_answer",
    "list_wrong_answers",
    "mark_resolved",
    "start_redo_session",
]
