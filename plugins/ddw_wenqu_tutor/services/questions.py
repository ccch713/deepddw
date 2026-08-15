"""真题题库（按知识点/年份/难度索引 + 评判）。"""
from __future__ import annotations

import json
import re
import time
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wenqu_tutor.models import (
    WenquProgress,
    WenquQuestion,
    WenquWrongAnswer,
)
from plugins.ddw_wenqu_tutor.prompt.chem_modes import identify_mode

# error_type 扩展枚举（原 4 值 + 新增 7 值化学环节级）
CHEM_ERROR_TYPES: list[str] = [
    "concept", "calculation", "unit", "misread",
    "misread_condition", "wrong_reaction",
    "overage_missed", "conservation_fail",
    "valence", "electron_transfer", "expression",
]


def generate_question_id() -> str:
    """生成题目 ID。"""
    return f"Q{int(time.time() * 1000)}{uuid.uuid4().hex[:6]}"


def generate_wrong_id() -> str:
    """生成错题 ID。"""
    return f"W{int(time.time() * 1000)}{uuid.uuid4().hex[:6]}"


async def list_questions(
    db: AsyncSession,
    subject: Optional[str] = None,
    chapter: Optional[str] = None,
    difficulty: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[WenquQuestion], int]:
    """查询题目列表。"""
    query = select(WenquQuestion)

    if subject:
        query = query.where(
            WenquQuestion.subject == subject
        )
    if chapter:
        query = query.where(
            WenquQuestion.chapter == chapter
        )
    if difficulty:
        query = query.where(
            WenquQuestion.difficulty == difficulty
        )

    # 总数
    count_query = select(func.count()).select_from(
        query.subquery()
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 分页
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    questions = list(result.scalars().all())

    return questions, total


async def list_questions_by_mastery(
    db: AsyncSession,
    student_name: str,
    mastery: str,
    subject: Optional[str] = None,
    chapter: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[tuple[WenquQuestion, int]], int]:
    """按学生掌握度筛选题目（2026-08-14 用户拍板：难度=错误次数）。

    掌握度三档（错误次数 = 该生该题的累计错题记录数）：
    - weak:     错误 ≥ 3 次（未掌握）→ 薄弱优先
    - medium:   错误 1-2 次 → 巩固
    - mastered: 已标记 resolved 的错题 → 复习
    """
    from plugins.ddw_wenqu_tutor.models import (
        WenquWrongAnswer,
    )

    # 该生所有错题按题目聚合计数 + resolved 状态
    result = await db.execute(
        select(
            WenquWrongAnswer.question_id,
            func.count(WenquWrongAnswer.id),
            func.max(WenquWrongAnswer.resolved),
        )
        .where(WenquWrongAnswer.student_name == student_name)
        .group_by(WenquWrongAnswer.question_id)
    )
    stats = {
        qid: {"count": cnt, "resolved": bool(res)}
        for qid, cnt, res in result.all()
    }

    # 计算符合条件的题目集合（保留错误次数供展示）
    matched: dict[str, int] = {}
    for qid, s in stats.items():
        if mastery == "weak" and s["count"] >= 3 and not s["resolved"]:
            matched[qid] = s["count"]
        elif mastery == "medium" and 1 <= s["count"] <= 2 and not s["resolved"]:
            matched[qid] = s["count"]
        elif mastery == "mastered" and s["resolved"]:
            matched[qid] = s["count"]
    if not matched:
        return [], 0

    # 查询题目本体（保留题目与错误次数的映射）
    query = select(WenquQuestion).where(
        WenquQuestion.id.in_(matched.keys())
    )
    if subject:
        query = query.where(WenquQuestion.subject == subject)
    if chapter:
        query = query.where(WenquQuestion.chapter == chapter)

    total_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = total_result.scalar() or 0

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    questions = list(result.scalars().all())

    return [(q, matched.get(q.id, 0)) for q in questions], total


async def get_question(
    db: AsyncSession, question_id: str
) -> Optional[WenquQuestion]:
    """获取单个题目。"""
    result = await db.execute(
        select(WenquQuestion).where(
            WenquQuestion.id == question_id
        )
    )
    return result.scalar_one_or_none()


async def judge_answer(
    db: AsyncSession,
    question_id: str,
    student_answer: str,
    session_id: Optional[str] = None,
    llm_client=None,
    student_name: str = "CXY",
) -> dict:
    """评判答案（答错→错题本+四问；每次答题记 Attempt）。

    化学题：LLM 结构化评判（四问 + error_type + mode）
    物理题：原逻辑不变

    Returns:
        dict with keys: correct, error_type,
        knowledge_gap, wrong_id, four_questions, mode
    """
    question = await get_question(db, question_id)
    if not question:
        raise ValueError(f"Question {question_id} not found")

    is_chemistry = question.subject == "chemistry"

    if is_chemistry and llm_client:
        result = await _judge_chemistry(
            db, question, student_answer, session_id, llm_client,
        )
    elif question.subject != "physics" and llm_client:
        # 新 5 科（语文/数学/英语/道法/历史）走通用判断器（角色按科目注册表）
        result = await _judge_generic(
            db, question, student_answer, session_id, llm_client,
        )
    else:
        result = await _judge_physics(
            db, question, student_answer, session_id,
        )

    # 答题记录（挑战模式排除已作对的题；掌握度数据源）
    from plugins.ddw_wenqu_tutor.models import WenquAttempt

    db.add(
        WenquAttempt(
            student_name=student_name,
            question_id=question_id,
            correct=bool(result.get("correct", False)),
        )
    )
    await db.commit()

    return result


async def list_challenge_questions(
    db: AsyncSession,
    student_name: str = "CXY",
    subject: Optional[str] = None,
    chapter: Optional[str] = None,
    limit: int = 20,
) -> tuple[list[tuple[WenquQuestion, int]], int]:
    """挑战模式（2026-08-14 用户拍板）：全用户错误次数最多的公共题。

    筛选：排除该生已作对的题；按全用户错题计数降序。
    对外口径：AI 根据学生错题类型自动生成的练习题。
    备注：公共库地区分类（考纲差异）为 M1 需求，已记录规划文档。
    """
    from plugins.ddw_wenqu_tutor.models import (
        WenquAttempt,
        WenquWrongAnswer,
    )

    # 全用户错题聚合计数（公共难度榜）
    result = await db.execute(
        select(
            WenquWrongAnswer.question_id,
            func.count(WenquWrongAnswer.id),
        )
        .group_by(WenquWrongAnswer.question_id)
    )
    hot_rank = dict(result.all())
    if not hot_rank:
        return [], 0

    # 该生已作对的题（排除）
    result = await db.execute(
        select(WenquAttempt.question_id).where(
            WenquAttempt.student_name == student_name,
            WenquAttempt.correct.is_(True),
        )
    )
    solved_ids = {qid for qid in result.scalars().all()}

    # 排序：错误次数降序 → 取前 limit 个候选
    candidates = [
        qid for qid, cnt in hot_rank.items()
        if qid not in solved_ids
    ]
    candidates.sort(key=lambda qid: hot_rank[qid], reverse=True)
    candidates = candidates[:limit]

    if not candidates:
        return [], 0

    query = select(WenquQuestion).where(
        WenquQuestion.id.in_(candidates)
    )
    if subject:
        query = query.where(WenquQuestion.subject == subject)
    if chapter:
        query = query.where(WenquQuestion.chapter == chapter)

    result = await db.execute(query)
    questions = list(result.scalars().all())
    # 保持热度顺序
    questions.sort(key=lambda q: candidates.index(q.id))
    return [(q, hot_rank.get(q.id, 0)) for q in questions], len(questions)


async def _judge_chemistry(
    db: AsyncSession,
    question: WenquQuestion,
    student_answer: str,
    session_id: Optional[str],
    llm_client,
) -> dict:
    """化学题 LLM 结构化评判。"""
    mode = question.mode or identify_mode(
        question.question_text, question.knowledge_points,
    )

    judge_prompt = f"""\
你是化学教师林若薇。请评判学生的答案。

【题目】
{question.question_text}

【标准答案】
{question.answer}

【学生答案】
{student_answer}

【评判要求】
请严格按以下 JSON 格式输出，不要输出其他内容：
{{
  "correct": true/false,
  "error_type": "概念错误|计算错误|单位错误|审题失误|方程式错误|过量判断失误|守恒不守恒|化合价错误|电子转移错误|表达不规范|null",
  "correct_parts": "学生做对了什么（正确答案时填'全部正确'）",
  "error_location": "第一处关键错误的位置描述",
  "error_root_cause": "错误根因分析",
  "check_strategy": "下次如何避免此类错误"
}}

error_type 取值说明：
- 正确时填 null
- 概念错误=concept, 计算错误=calculation, 单位错误=unit
- 审题失误=misread_condition, 方程式错误=wrong_reaction
- 过量判断失误=overage_missed, 守恒不守恒=conservation_fail
- 化合价错误=valence, 电子转移错误=electron_transfer
- 表达不规范=expression, 审题错误=misread

内容中的引号一律使用中文引号“”，禁止使用英文双引号（避免 JSON 断裂）。
"""

    response = await llm_client.generate(
        model="MiniMax-M3",
        system="你是化学评判助手，严格输出 JSON。",
        user=judge_prompt,
        temperature=0.1,
        max_tokens=500,
    )

    try:
        parsed = json.loads(_extract_json(response))
    except (json.JSONDecodeError, TypeError):
        return await _judge_physics(
            db, question, student_answer, session_id,
        )

    correct = parsed.get("correct", False)
    error_type_raw = parsed.get("error_type")
    error_type = _map_error_type(error_type_raw)
    four_questions = None

    if not correct:
        four_questions = {
            "correct_parts": parsed.get("correct_parts", ""),
            "error_location": parsed.get("error_location", ""),
            "error_root_cause": parsed.get("error_root_cause", ""),
            "check_strategy": parsed.get("check_strategy", ""),
        }

        wrong_id = generate_wrong_id()
        wrong = WenquWrongAnswer(
            id=wrong_id,
            student_name="CXY",
            question_id=question.id,
            session_id=session_id,
            student_answer=student_answer,
            error_type=error_type,
            knowledge_gap=question.knowledge_points or "待分析",
            correct_parts=four_questions["correct_parts"],
            error_location=four_questions["error_location"],
            error_root_cause=four_questions["error_root_cause"],
            check_strategy=four_questions["check_strategy"],
            mode=mode,
            resolved=False,
        )
        db.add(wrong)
        await _update_progress(
            db, "CXY", question.subject, question.chapter, False,
        )
        await db.commit()

        return {
            "correct": False,
            "error_type": error_type,
            "knowledge_gap": question.knowledge_points,
            "wrong_id": wrong_id,
            "four_questions": four_questions,
            "mode": mode,
        }

    await _update_progress(
        db, "CXY", question.subject, question.chapter, True,
    )
    await db.commit()

    return {
        "correct": True,
        "error_type": None,
        "knowledge_gap": None,
        "wrong_id": None,
        "four_questions": None,
        "mode": mode,
    }


async def _judge_generic(
    db: AsyncSession,
    question: WenquQuestion,
    student_answer: str,
    session_id: Optional[str],
    llm_client,
) -> dict:
    """通用 LLM 结构化评判（语文/数学/英语/道法/历史，角色按科目注册表）。"""
    from plugins.ddw_wenqu_tutor.prompt.subject_meta import SUBJECTS

    meta = SUBJECTS.get(question.subject, {})
    judge_role = meta.get("judge_role") or "学科教师"

    judge_prompt = f"""\
你是{judge_role}。请评判学生的答案。

【题目】
{question.question_text}

【标准答案】
{question.answer}

【学生答案】
{student_answer}

【评判要求】
请严格按以下 JSON 格式输出，不要输出其他内容：
{{
  "correct": true/false,
  "error_type": "概念错误|计算错误|审题失误|表达不规范|null",
  "correct_parts": "学生做对了什么（正确答案时填'全部正确'）",
  "error_location": "第一处关键错误的位置描述",
  "error_root_cause": "错误根因分析",
  "check_strategy": "下次如何避免此类错误"
}}

error_type 取值说明：
- 正确时填 null
- 概念错误=concept, 计算错误=calculation
- 审题失误=misread, 表达不规范=expression

内容中的引号一律使用中文引号“”，禁止使用英文双引号（避免 JSON 断裂）。
"""

    response = await llm_client.generate(
        model="MiniMax-M3",
        system=f"你是{judge_role}，严格输出 JSON。",
        user=judge_prompt,
        temperature=0.1,
        max_tokens=500,
    )

    try:
        parsed = json.loads(_extract_json(response))
    except (json.JSONDecodeError, TypeError):
        return await _judge_physics(
            db, question, student_answer, session_id,
        )

    correct = parsed.get("correct", False)
    error_type = _map_error_type(parsed.get("error_type"))
    mode = question.mode

    if not correct:
        four_questions = {
            "correct_parts": parsed.get("correct_parts", ""),
            "error_location": parsed.get("error_location", ""),
            "error_root_cause": parsed.get("error_root_cause", ""),
            "check_strategy": parsed.get("check_strategy", ""),
        }
        wrong_id = generate_wrong_id()
        wrong = WenquWrongAnswer(
            id=wrong_id,
            student_name="CXY",
            question_id=question.id,
            session_id=session_id,
            student_answer=student_answer,
            error_type=error_type,
            knowledge_gap=question.knowledge_points or "待分析",
            correct_parts=four_questions["correct_parts"],
            error_location=four_questions["error_location"],
            error_root_cause=four_questions["error_root_cause"],
            check_strategy=four_questions["check_strategy"],
            mode=mode,
            resolved=False,
        )
        db.add(wrong)
        await _update_progress(
            db, "CXY", question.subject, question.chapter, False,
        )
        await db.commit()

        return {
            "correct": False,
            "error_type": error_type,
            "knowledge_gap": question.knowledge_points,
            "wrong_id": wrong_id,
            "four_questions": four_questions,
            "mode": mode,
        }

    await _update_progress(
        db, "CXY", question.subject, question.chapter, True,
    )
    await db.commit()

    return {
        "correct": True,
        "error_type": None,
        "knowledge_gap": None,
        "wrong_id": None,
        "four_questions": None,
        "mode": mode,
    }


async def _judge_physics(
    db: AsyncSession,
    question: WenquQuestion,
    student_answer: str,
    session_id: Optional[str],
) -> dict:
    """物理题评判（原逻辑保持不变）。"""
    correct_answer = question.answer.strip()
    student_clean = student_answer.strip()
    correct = (
        student_clean == correct_answer
        or correct_answer in student_clean
        or student_clean in correct_answer
    )

    error_type = None
    knowledge_gap = None
    wrong_id = None

    if not correct:
        error_type = _analyze_error_type(student_answer, question)
        knowledge_gap = question.knowledge_points or "待分析"
        wrong_id = generate_wrong_id()
        wrong = WenquWrongAnswer(
            id=wrong_id,
            student_name="CXY",
            question_id=question.id,
            session_id=session_id,
            student_answer=student_answer,
            error_type=error_type,
            knowledge_gap=knowledge_gap,
            resolved=False,
        )
        db.add(wrong)

    await _update_progress(
        db, "CXY", question.subject, question.chapter, correct,
    )
    await db.commit()

    return {
        "correct": correct,
        "error_type": error_type,
        "knowledge_gap": knowledge_gap,
        "wrong_id": wrong_id,
        "four_questions": None,
        "mode": None,
    }


def _analyze_error_type(
    student_answer: str, question: WenquQuestion
) -> str:
    """分析错误类型。"""
    answer_lower = student_answer.lower()
    correct_lower = question.answer.lower()

    # 单位错误
    units = ["m/s", "kg", "n", "j", "w", "pa", "v", "a"]
    for unit in units:
        if unit in answer_lower and unit not in correct_lower:
            return "unit"

    # 计算错误（数字接近但不对）
    student_nums = re.findall(r"[\d.]+", student_answer)
    correct_nums = re.findall(r"[\d.]+", question.answer)
    if student_nums and correct_nums:
        try:
            s = float(student_nums[0])
            c = float(correct_nums[0])
            if 0.5 < s / c < 2:
                return "calculation"
        except (ValueError, ZeroDivisionError):
            pass

    return "concept"


def _map_error_type(raw: Optional[str]) -> str:
    """将 LLM 返回的中文错误类型映射到英文枚举。"""
    mapping = {
        "概念错误": "concept",
        "计算错误": "calculation",
        "单位错误": "unit",
        "审题失误": "misread_condition",
        "方程式错误": "wrong_reaction",
        "过量判断失误": "overage_missed",
        "守恒不守恒": "conservation_fail",
        "化合价错误": "valence",
        "电子转移错误": "electron_transfer",
        "表达不规范": "expression",
        "审题错误": "misread",
    }
    if raw is None:
        return "concept"
    return mapping.get(raw, raw)


async def _update_progress(
    db: AsyncSession,
    student_name: str,
    subject: str,
    chapter: str,
    correct: bool,
) -> None:
    """更新学习进度。"""
    result = await db.execute(
        select(WenquProgress).where(
            WenquProgress.student_name == student_name,
            WenquProgress.subject == subject,
            WenquProgress.chapter == chapter,
        )
    )
    progress = result.scalar_one_or_none()

    if not progress:
        progress = WenquProgress(
            student_name=student_name,
            subject=subject,
            chapter=chapter,
            total_questions=1,
            completed=1,
            correct_count=1 if correct else 0,
        )
        db.add(progress)
    else:
        progress.total_questions += 1
        progress.completed += 1
        if correct:
            progress.correct_count += 1


def _extract_json(text: str) -> str:
    """从 LLM 响应中提取 JSON（容错 markdown 代码块围栏）。"""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        return raw[start : end + 1]
    return raw


async def generate_variant(
    db: AsyncSession,
    question_id: str,
    difficulty: str = "medium",
    llm_client=None,
) -> dict:
    """AI 生成同类变式题（is_ai_generated=true 入库）。

    Returns:
        dict with keys: question_id, question_text,
        answer, explanation, mode, is_ai_generated
    """
    if llm_client is None:
        from ..llm_client import get_llm_client

        llm_client = get_llm_client()
    question = await get_question(db, question_id)
    if not question:
        raise ValueError(f"Question {question_id} not found")

    mode = question.mode or identify_mode(
        question.question_text, question.knowledge_points,
    )

    from plugins.ddw_wenqu_tutor.prompt.subject_meta import SUBJECTS

    variant_role = SUBJECTS.get(
        question.subject, {}
    ).get("variant_role") or "学科出题教师"

    variant_prompt = f"""\
你是{variant_role}。请根据以下题目生成一道同类变式题。

【原题】
{question.question_text}

【原题答案】
{question.answer}

【知识点】
{question.knowledge_points}

【难度】{difficulty}

【要求】
1. 题型和考查知识点相同，但具体数值/物质/情境不同
2. 难度为 {difficulty}
3. 必须给出标准答案和解析
4. 严格按以下 JSON 格式输出：
{{
  "question_text": "题目文本",
  "answer": "标准答案",
  "explanation": "解析",
  "knowledge_points": ["知识点1", "知识点2"]
}}
5. JSON 内容中的引号一律使用中文引号“”，禁止使用英文双引号（避免 JSON 断裂）
"""

    response = await llm_client.generate(
        model="MiniMax-M3",
        system=f"你是{variant_role}，严格输出 JSON。",
        user=variant_prompt,
        temperature=0.7,
        max_tokens=800,
    )

    # LLM 偶发输出非严格 JSON → 重试最多 2 次（M3 温度 0.7 有随机性）
    parsed = None
    for _attempt in range(3):
        if _attempt > 0:
            response = await llm_client.generate(
                model="MiniMax-M3",
                system=f"你是{variant_role}，严格输出 JSON。",
                user=variant_prompt,
                temperature=0.2,  # 重试降低温度提高格式稳定性
                max_tokens=800,
            )
        try:
            parsed = json.loads(_extract_json(response))
            break
        except (json.JSONDecodeError, TypeError):
            continue
    if parsed is None:
        raise ValueError("AI 变式题生成失败：输出无法解析（已重试 3 次）")

    new_id = generate_question_id()
    new_question = WenquQuestion(
        id=new_id,
        subject=question.subject,
        chapter=question.chapter,
        year=question.year,
        difficulty=difficulty,
        source="AI生成",
        question_text=parsed["question_text"],
        answer=parsed["answer"],
        explanation=parsed.get("explanation", ""),
        knowledge_points=json.dumps(
            parsed.get("knowledge_points", []),
            ensure_ascii=False,
        ),
        mode=mode,
        is_ai_generated=True,
    )
    db.add(new_question)
    await db.commit()

    return {
        "question_id": new_id,
        "question_text": parsed["question_text"],
        "answer": parsed["answer"],
        "explanation": parsed.get("explanation", ""),
        "mode": mode,
        "is_ai_generated": True,
    }


# 模式→关键词映射（用于旧数据回填）
_MODE_KEYWORDS: dict[str, list[str]] = {
    "substance_change": ["化学变化", "物理变化", "化合反应", "分解反应", "置换反应", "复分解反应"],
    "ion_redox": ["离子", "氧化", "还原", "得失电子", "化合价", "氧化剂", "还原剂"],
    "quant_calc": ["计算", "质量", "摩尔", "物质的量", "浓度", "质量分数"],
    "experiment": ["实验", "操作", "装置", "仪器", "气密性", "验满"],
    "test_identify": ["鉴别", "检验", "鉴定", "区分", "证明"],
    "purify_separate": ["提纯", "分离", "除杂", "净化"],
    "chart_table": ["图表", "曲线", "表格", "坐标", "趋势"],
    "process_flow": ["流程", "流程图", "工业", "生产", "制备"],
    "electrochem": ["原电池", "电解", "电极", "阳极", "阴极"],
    "structure": ["原子结构", "化学键", "离子键", "共价键", "晶体"],
    "organic": ["有机", "官能团", "甲烷", "乙烯", "乙醇", "乙酸"],
}


async def backfill_question_modes(
    db: AsyncSession,
) -> int:
    """回填旧 questions 的 mode 字段（按 knowledge_points 关键词匹配）。

    Returns:
        回填数量
    """
    from sqlalchemy import update

    result = await db.execute(
        select(WenquQuestion).where(
            WenquQuestion.subject == "chemistry",
            WenquQuestion.mode.is_(None),
        )
    )
    questions = list(result.scalars().all())

    count = 0
    for q in questions:
        kp = q.knowledge_points or ""
        text = f"{kp} {q.question_text}"
        best_mode = None
        best_score = 0
        for mode_key, keywords in _MODE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > best_score:
                best_score = score
                best_mode = mode_key

        if best_mode and best_score > 0:
            await db.execute(
                update(WenquQuestion)
                .where(WenquQuestion.id == q.id)
                .values(mode=best_mode)
            )
            count += 1

    await db.commit()
    return count


__all__ = [
    "CHEM_ERROR_TYPES",
    "backfill_question_modes",
    "generate_variant",
    "get_question",
    "judge_answer",
    "list_questions",
]
