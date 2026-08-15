"""数据面端点接线测试（2026-08-14 M0-2）。

覆盖 4 个新接线的端点（直接调用 handler + 内存异步库）：
- /textbook/list
- /questions/list
- /wrongbook/list
- /parent/stats
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

from core.database.models import Tenant
from core.database.tenant_filter import tenant_scope

from plugins.ddw_wenqu_tutor.models import (
    WenquAttempt,
    WenquBase,
    WenquProgress,
    WenquQuestion,
    WenquSession,
    WenquTextbook,
    WenquWrongAnswer,
)
from plugins.ddw_wenqu_tutor.router import (
    parent_stats,
    questions_list,
    textbook_list,
    wrongbook_list,
)

NOW = datetime.now(timezone.utc)


async def _seed(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(WenquBase.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        db.add(Tenant(id=1, name="家庭一"))
        db.add(
            WenquQuestion(
                id="Q1",
                subject="chemistry",
                chapter="燃料",
                year=2024,
                difficulty="easy",
                source="textbook",
                question_text="燃料有哪些？",
                answer="B",
                explanation="解析",
                knowledge_points='["燃料"]',
            )
        )
        db.add(
            WenquTextbook(
                id="TB1",
                subject="chemistry",
                grade="9",
                version="人教版 2024",
                file_path="/tmp/tb.pdf",
                chapters='[{"title": "燃料", "pages": "1-10"}]',
            )
        )
        db.add(
            WenquSession(
                id="WS1",
                student_name="CXY",
                subject="physics",
                status="active",
                started_at=NOW - timedelta(days=1),
                active_seconds=3600,  # 60 分钟
                message_count=5,
            )
        )
        db.add(
            WenquWrongAnswer(
                id="WR1",
                student_name="CXY",
                question_id="Q1",
                student_answer="A",
                error_type="concept",
                knowledge_gap="概念不清",
                resolved=False,
            )
        )
        db.add(
            WenquProgress(
                student_name="CXY",
                subject="physics",
                chapter="力学",
                total_questions=10,
                completed=8,
                correct_count=6,
            )
        )
        await db.commit()


@pytest.fixture
async def db_maker():
    engine = create_async_engine("sqlite+aiosqlite://")
    await _seed(engine)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_textbook_list(db_maker):
    async with db_maker() as db:
        with tenant_scope(1):
            resp = await textbook_list(db=db)
    assert resp["total"] == 1
    assert resp["items"][0]["id"] == "TB1"
    assert resp["items"][0]["version"] == "人教版 2024"


@pytest.mark.asyncio
async def test_questions_list_filter(db_maker):
    async with db_maker() as db:
        with tenant_scope(1):
            resp = await questions_list(subject="chemistry", db=db)
    assert resp.total == 1
    assert resp.items[0]["id"] == "Q1"
    assert resp.items[0]["question_text"] == "燃料有哪些？"


@pytest.mark.asyncio
async def test_questions_list_no_match(db_maker):
    async with db_maker() as db:
        with tenant_scope(1):
            resp = await questions_list(subject="physics", db=db)
    assert resp.total == 0
    assert resp.items == []


@pytest.mark.asyncio
async def test_wrongbook_list(db_maker):
    async with db_maker() as db:
        with tenant_scope(1):
            resp = await wrongbook_list(student_name="CXY", db=db)
    assert resp["total"] == 1
    assert resp["items"][0]["id"] == "WR1"
    assert resp["items"][0]["resolved"] is False


@pytest.mark.asyncio
async def test_parent_stats(db_maker):
    async with db_maker() as db:
        with tenant_scope(1):
            resp = await parent_stats(student_name="CXY", days=7, db=db)
    # 60 分钟活跃 → 总分钟 60；做 8 题对 6 → 正确率 0.75
    assert resp.total_minutes_week >= 60
    assert resp.questions_attempted_week == 8
    assert resp.correct_rate == pytest.approx(0.75)


# ── M0-5.1 掌握度筛选（难度=错误次数，用户拍板 2026-08-14）──

async def _seed_mastery(engine) -> None:
    """题库 4 题 + 错题记录（Q1 错 3 次未掌握 / Q2 错 1 次 / Q3 错 1 次已掌握 / Q4 无记录）。"""
    async with engine.begin() as conn:
        await conn.run_sync(WenquBase.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        db.add(Tenant(id=1, name="家庭一"))
        for i in range(1, 5):
            db.add(
                WenquQuestion(
                    id=f"MQ{i}",
                    subject="chemistry",
                    chapter="燃料",
                    year=2024,
                    difficulty="medium",
                    source="textbook",
                    question_text=f"掌握度测试题{i}",
                    answer="B",
                    knowledge_points="[]",
                )
            )
        # Q1 错 3 次（weak）
        for i in range(3):
            db.add(WenquWrongAnswer(
                id=f"MW1_{i}", student_name="CXY", question_id="MQ1",
                student_answer="A", error_type="concept",
                knowledge_gap="x", resolved=False,
            ))
        # Q2 错 1 次（medium）
        db.add(WenquWrongAnswer(
            id="MW2", student_name="CXY", question_id="MQ2",
            student_answer="A", error_type="concept",
            knowledge_gap="x", resolved=False,
        ))
        # Q3 错 1 次已掌握（mastered）
        db.add(WenquWrongAnswer(
            id="MW3", student_name="CXY", question_id="MQ3",
            student_answer="A", error_type="concept",
            knowledge_gap="x", resolved=True,
        ))
        await db.commit()


@pytest.fixture
async def mastery_maker():
    engine = create_async_engine("sqlite+aiosqlite://")
    await _seed_mastery(engine)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_mastery_weak(mastery_maker):
    """错误≥3次：只返回 MQ1，带 wrong_count=3。"""
    async with mastery_maker() as db:
        with tenant_scope(1):
            resp = await questions_list(
                mastery="weak", student_name="CXY", db=db,
            )
    assert resp.total == 1
    assert resp.items[0]["id"] == "MQ1"
    assert resp.items[0]["wrong_count"] == 3


@pytest.mark.asyncio
async def test_mastery_medium(mastery_maker):
    """错误1-2次：返回 MQ2。"""
    async with mastery_maker() as db:
        with tenant_scope(1):
            resp = await questions_list(
                mastery="medium", student_name="CXY", db=db,
            )
    assert resp.total == 1
    assert resp.items[0]["id"] == "MQ2"


@pytest.mark.asyncio
async def test_mastery_mastered(mastery_maker):
    """已掌握：返回 MQ3。"""
    async with mastery_maker() as db:
        with tenant_scope(1):
            resp = await questions_list(
                mastery="mastered", student_name="CXY", db=db,
            )
    assert resp.total == 1
    assert resp.items[0]["id"] == "MQ3"


@pytest.mark.asyncio
async def test_mastery_no_record(mastery_maker):
    """无错题记录的学生：三档都为空。"""
    async with mastery_maker() as db:
        with tenant_scope(1):
            resp = await questions_list(
                mastery="weak", student_name="OTHER", db=db,
            )
    assert resp.total == 0


# ── 挑战模式（全用户错误榜，2026-08-14）──

async def _seed_challenge(engine) -> None:
    """题库 4 题：Q1 全站错 5 次 / Q2 全站错 2 次 / Q3 全站错 1 次；
    CXY 已作对 Q1（attempt correct），OTHER 无记录。"""
    async with engine.begin() as conn:
        await conn.run_sync(WenquBase.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        db.add(Tenant(id=1, name="家庭一"))
        for i in range(1, 4):
            db.add(
                WenquQuestion(
                    id=f"CQ{i}",
                    subject="chemistry",
                    chapter="燃料",
                    year=2024,
                    difficulty="medium",
                    source="textbook",
                    question_text=f"挑战测试题{i}",
                    answer="B",
                    knowledge_points="[]",
                )
            )
        # 全站错误：Q1×5（CXY 2 次 + OTHER 3 次）、Q2×2（OTHER）、Q3×1（OTHER）
        for i in range(2):
            db.add(WenquWrongAnswer(
                id=f"CW1_{i}", student_name="CXY", question_id="CQ1",
                student_answer="A", error_type="concept",
                knowledge_gap="x", resolved=False,
            ))
        for i in range(3):
            db.add(WenquWrongAnswer(
                id=f"CW1O_{i}", student_name="OTHER", question_id="CQ1",
                student_answer="A", error_type="concept",
                knowledge_gap="x", resolved=False,
            ))
        for i in range(2):
            db.add(WenquWrongAnswer(
                id=f"CW2_{i}", student_name="OTHER", question_id="CQ2",
                student_answer="A", error_type="concept",
                knowledge_gap="x", resolved=False,
            ))
        db.add(WenquWrongAnswer(
            id="CW3", student_name="OTHER", question_id="CQ3",
            student_answer="A", error_type="concept",
            knowledge_gap="x", resolved=False,
        ))
        # CXY 已作对 CQ1
        db.add(WenquAttempt(
            student_name="CXY", question_id="CQ1", correct=True,
        ))
        await db.commit()


@pytest.fixture
async def challenge_maker():
    engine = create_async_engine("sqlite+aiosqlite://")
    await _seed_challenge(engine)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.mark.asyncio
async def test_challenge_excludes_solved_and_ranks(challenge_maker):
    """挑战：排除已作对 CQ1；按全站错误数降序 → CQ2(2) 先于 CQ3(1)。"""
    async with challenge_maker() as db:
        with tenant_scope(1):
            from plugins.ddw_wenqu_tutor.router import (
                questions_challenge,
            )

            resp = await questions_challenge(
                student_name="CXY", db=db,
            )
    assert resp.total == 2
    assert resp.items[0]["id"] == "CQ2"
    assert resp.items[0]["wrong_count"] == 2
    assert resp.items[1]["id"] == "CQ3"
    assert resp.items[1]["wrong_count"] == 1


@pytest.mark.asyncio
async def test_challenge_new_student_all(challenge_maker):
    """无作对记录的学生：Q1(5) → Q2(2) → Q3(1) 全量热度排序。"""
    async with challenge_maker() as db:
        with tenant_scope(1):
            from plugins.ddw_wenqu_tutor.router import (
                questions_challenge,
            )

            resp = await questions_challenge(
                student_name="NEW", db=db,
            )
    assert resp.total == 3
    assert resp.items[0]["id"] == "CQ1"
    assert resp.items[0]["wrong_count"] == 5


# ── 题目元数据（2026-08-14：年份默认当前年 + M1 地域/学校字段）──

@pytest.mark.asyncio
async def test_question_year_defaults_to_current(db_maker):
    """不传 year 入库时默认当前年份（教改频繁，老题需标注）。"""
    from datetime import datetime

    from plugins.ddw_wenqu_tutor.models import WenquQuestion

    async with db_maker() as db:
        with tenant_scope(1):
            db.add(WenquQuestion(
                id="YQ1",
                subject="chemistry",
                chapter="燃料",
                difficulty="easy",
                source="textbook",
                question_text="年份默认测试",
                answer="B",
                knowledge_points="[]",
            ))
            await db.commit()
        with tenant_scope(1):
            q = await db.get(WenquQuestion, "YQ1")
            assert q.year == datetime.now().year


def test_question_meta_columns_present():
    """M1 预留列：province/city/school/contributor。"""
    from sqlalchemy import inspect

    cols = {c.name for c in inspect(WenquQuestion).columns}
    for col in ("province", "city", "school", "contributor"):
        assert col in cols, f"缺少 {col}"
