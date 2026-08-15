"""老版问渠页面适配层（2026-08-14 移植 wenquK12 页面）。

wenquK12 前端页面（parent/ocr/game/mistake/settings）已移植到
紫色版项目，本模块提供其期望的端点数据（从插件版数据聚合），
避免重写老页面逻辑。

M0 说明：登录为 M1（微信服务号 OAuth），演示模式 token
'__wenqu_m0_demo__' 直接返回学生档案。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_wenqu_tutor.models import (
    WenquQuestion,
    WenquSession,
    WenquWrongAnswer,
)

DEMO_TOKEN = "__wenqu_m0_demo__"
DEMO_STUDENT = "CXY"

CARELESS_NAMES = {
    "concept": "概念不清", "calculation": "计算失误", "unit": "单位换算",
    "misread": "审题不清", "misread_condition": "条件遗漏",
    "wrong_reaction": "反应写错", "overage_missed": "过量漏判",
    "conservation_fail": "守恒失配", "valence": "化合价错",
    "electron_transfer": "电子转移错", "expression": "表达不规范",
    "logic": "逻辑错误", "time": "时间紧张",
}


def is_demo_token(token: Optional[str]) -> bool:
    """M0 演示模式：demo token 或缺失。"""
    return token in (None, "", DEMO_TOKEN)


async def build_weekly_report(
    db: AsyncSession,
    student_name: str = DEMO_STUDENT,
) -> dict:
    """构建家长周报（老页面格式）。"""
    now = datetime.now(timezone.utc)
    days_since_monday = now.weekday()
    week_start = (now - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # 各科学习时长/消息数（wenqu_sessions）
    result = await db.execute(
        select(
            WenquSession.subject,
            func.sum(WenquSession.active_seconds).label("total_seconds"),
            func.sum(WenquSession.message_count).label("total_messages"),
        )
        .where(
            WenquSession.student_name == student_name,
            WenquSession.created_at >= week_start,
        )
        .group_by(WenquSession.subject)
    )
    subject_stats = {}
    for row in result.all():
        subject_stats[row.subject] = {
            "total_seconds": int(row.total_seconds or 0),
            "total_minutes": int((row.total_seconds or 0) // 60),
            "total_messages": int(row.total_messages or 0),
            "total_cost_cents": 0,  # 用量计费明细 M1 汇总
        }

    # 错题数 + 章节弱项 + 粗心分布
    result = await db.execute(
        select(
            WenquQuestion.chapter,
            WenquWrongAnswer.error_type,
            func.count(WenquWrongAnswer.id),
        )
        .join(
            WenquQuestion,
            WenquQuestion.id == WenquWrongAnswer.question_id,
        )
        .where(
            WenquWrongAnswer.student_name == student_name,
            WenquWrongAnswer.created_at >= week_start,
        )
        .group_by(WenquQuestion.chapter, WenquWrongAnswer.error_type)
    )
    chapter_cnt: dict[str, int] = {}
    careless_cnt: dict[str, int] = {}
    mistake_count = 0
    for chapter, etype, cnt in result.all():
        mistake_count += int(cnt)
        chapter_cnt[chapter or "未分类"] = chapter_cnt.get(chapter or "未分类", 0) + int(cnt)
        careless_cnt[etype or "concept"] = careless_cnt.get(etype or "concept", 0) + int(cnt)

    weak_chapters = [
        {"chapter": ch, "count": c}
        for ch, c in sorted(chapter_cnt.items(), key=lambda x: -x[1])[:5]
    ]
    careless_stats = [
        {"type": t, "count": c}
        for t, c in sorted(careless_cnt.items(), key=lambda x: -x[1])[:5]
    ]

    total_minutes = sum(s.get("total_minutes", 0) for s in subject_stats.values())
    if total_minutes >= 300:
        evaluation = "本周学习非常充实，孩子表现很棒"
    elif total_minutes >= 180:
        evaluation = "本周学习稳定，保持节奏"
    elif total_minutes >= 60:
        evaluation = "本周学习时间偏少，建议增加"
    else:
        evaluation = "本周学习时间不足，需要关注"

    return {
        "week_start": week_start.isoformat(),
        "week_end": now.isoformat(),
        "student_name": student_name,
        "is_test_user": False,
        "summary": {
            "total_minutes": total_minutes,
            "total_cost_yuan": 0.0,
            "mistake_count": mistake_count,
            "evaluation": evaluation,
        },
        "subject_breakdown": subject_stats,
        "weak_chapters": weak_chapters,
        "careless_breakdown": careless_stats,
        "suggestions": _generate_suggestions(
            subject_stats, weak_chapters, careless_stats,
        ),
    }


def _generate_suggestions(
    subject_stats: dict,
    weak_chapters: list,
    careless_stats: list,
) -> list:
    """生成家长建议（移植 wenquK12 规则）。"""
    suggestions = []
    if weak_chapters:
        top = weak_chapters[0]
        suggestions.append(
            f"本周错题集中在「{top['chapter']}」（{top['count']}道），建议下周重点复习这个章节"
        )
    if careless_stats:
        top = careless_stats[0]
        name = CARELESS_NAMES.get(top["type"], top["type"])
        suggestions.append(
            f"本周粗心最多的是「{name}」（{top['count']}次），建议专项训练"
        )
    physics = subject_stats.get("physics", {}).get("total_minutes", 0)
    chemistry = subject_stats.get("chemistry", {}).get("total_minutes", 0)
    if physics < 60 and chemistry < 60:
        suggestions.append("本周物理化学学习时间都不足，建议每天保证至少 30 分钟")
    elif abs(physics - chemistry) > 120:
        weaker = "物理" if physics < chemistry else "化学"
        suggestions.append(f"本周{weaker}学习时间偏少，建议平衡两科")
    if not suggestions:
        suggestions.append("本周整体不错，继续保持节奏，下周可以挑战更多新题")
    return suggestions


__all__ = [
    "DEMO_STUDENT",
    "DEMO_TOKEN",
    "build_weekly_report",
    "is_demo_token",
]
