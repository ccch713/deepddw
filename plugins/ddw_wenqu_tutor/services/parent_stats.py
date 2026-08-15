"""家长面板统计（周报数据源）。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wenqu_tutor.models import (
    WenquProgress,
    WenquSession,
    WenquWrongAnswer,
)


async def get_weekly_stats(
    db: AsyncSession,
    student_name: str = "CXY",
    days: int = 7,
) -> dict:
    """获取周统计数据。

    Returns:
        dict with keys: total_minutes_week,
        questions_attempted_week, correct_rate,
        weak_points, wrong_trend
    """
    # 计算时间范围
    now = datetime.now(timezone.utc)
    start_date = now - timedelta(days=days)

    # 活跃时长统计
    result = await db.execute(
        select(
            func.sum(WenquSession.active_seconds)
        ).where(
            WenquSession.student_name == student_name,
            WenquSession.created_at >= start_date,
        )
    )
    total_seconds = result.scalar() or 0
    total_minutes = total_seconds // 60

    # 题目统计
    result = await db.execute(
        select(
            func.count(WenquProgress.id),
            func.sum(WenquProgress.completed),
            func.sum(WenquProgress.correct_count),
        ).where(
            WenquProgress.student_name == student_name,
            WenquProgress.updated_at >= start_date,
        )
    )
    row = result.one()
    questions_attempted = row[1] or 0
    correct_count = row[2] or 0
    correct_rate = (
        correct_count / questions_attempted
        if questions_attempted > 0
        else 0.0
    )

    # 弱项分析
    result = await db.execute(
        select(
            WenquProgress.chapter,
            WenquProgress.total_questions,
            WenquProgress.correct_count,
        )
        .where(
            WenquProgress.student_name == student_name,
            WenquProgress.total_questions > 0,
        )
        .order_by(
            (
                WenquProgress.correct_count
                / WenquProgress.total_questions
            )
        )
        .limit(5)
    )
    weak_points = []
    for row in result:
        chapter, total, correct = row
        rate = correct / total if total > 0 else 0
        weak_points.append(
            {
                "point": chapter,
                "rate": round(rate, 2),
            }
        )

    # 错题趋势（按天）
    wrong_trend = []
    for i in range(days):
        day_start = start_date + timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        result = await db.execute(
            select(func.count(WenquWrongAnswer.id)).where(
                WenquWrongAnswer.student_name
                == student_name,
                WenquWrongAnswer.created_at >= day_start,
                WenquWrongAnswer.created_at < day_end,
            )
        )
        count = result.scalar() or 0
        wrong_trend.append(
            {
                "date": day_start.strftime("%Y-%m-%d"),
                "count": count,
            }
        )

    return {
        "total_minutes_week": total_minutes,
        "questions_attempted_week": questions_attempted,
        "correct_rate": round(correct_rate, 2),
        "weak_points": weak_points,
        "wrong_trend": wrong_trend,
    }


async def generate_weekly_report(
    db: AsyncSession,
    student_name: str = "CXY",
    llm_client=None,
) -> dict:
    """生成周报。"""
    stats = await get_weekly_stats(
        db, student_name, days=7
    )

    # LLM 生成摘要
    summary = "本周学习情况良好，继续保持。"
    if llm_client:
        prompt = (
            f"学生 {student_name} 本周学习统计：\n"
            f"- 活跃时长：{stats['total_minutes_week']} 分钟\n"
            f"- 做题数：{stats['questions_attempted_week']}\n"
            f"- 正确率：{stats['correct_rate']:.0%}\n"
            f"- 弱项：{stats['weak_points']}\n\n"
            "请用 2-3 句话总结本周学习情况，"
            "指出亮点和需要改进的地方。"
        )
        summary = await llm_client.generate(
            model="MiniMax-M3",
            user=prompt,
            max_tokens=200,
        )

    return {
        **stats,
        "summary_text": summary,
    }


__all__ = ["get_weekly_stats", "generate_weekly_report"]
