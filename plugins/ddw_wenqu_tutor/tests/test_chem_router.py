"""M5 路由分支+回填测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from plugins.ddw_wenqu_tutor.models import (
    WenquQuestion,
    WenquSession,
)
from plugins.ddw_wenqu_tutor.prompt.chemistry_safety import SAFETY_RULES
from plugins.ddw_wenqu_tutor.services.questions import (
    backfill_question_modes,
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def chem_session():
    return WenquSession(
        id="WS_CHEM_001",
        student_name="CXY",
        subject="chemistry",
        chapter="氧化还原",
        phase="info_check",
    )


@pytest.fixture
def physics_session():
    return WenquSession(
        id="WS_PHY_001",
        student_name="CXY",
        subject="physics",
        chapter="力学",
    )


@pytest.mark.asyncio
async def test_backfill_modes(mock_db):
    """回填旧数据 mode 字段。"""
    q1 = WenquQuestion(
        id="Q_BF_1",
        subject="chemistry",
        chapter="test",
        year=2025,
        difficulty="medium",
        source="test",
        question_text="判断氧化还原反应",
        answer="test",
        knowledge_points='["氧化还原", "化合价"]',
    )
    q2 = WenquQuestion(
        id="Q_BF_2",
        subject="chemistry",
        chapter="test",
        year=2025,
        difficulty="medium",
        source="test",
        question_text="计算生成物质量",
        answer="test",
        knowledge_points='["计算", "质量"]',
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [q1, q2]
    mock_db.execute.return_value = mock_result

    count = await backfill_question_modes(mock_db)
    assert count == 2
    assert mock_db.commit.called


@pytest.mark.asyncio
async def test_backfill_no_match(mock_db):
    """回填：无匹配关键词不设置 mode。"""
    q = WenquQuestion(
        id="Q_BF_3",
        subject="chemistry",
        chapter="test",
        year=2025,
        difficulty="medium",
        source="test",
        question_text="这是一道没有关键词的题目",
        answer="test",
        knowledge_points='["未知知识点"]',
    )

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [q]
    mock_db.execute.return_value = mock_result

    count = await backfill_question_modes(mock_db)
    assert count == 0


def test_safety_rules_endpoint_data():
    """安全规则端点数据完整性。"""
    assert len(SAFETY_RULES) == 20
    substances = [r["substance"] for r in SAFETY_RULES]
    assert "浓硫酸" in str(substances)
    assert "金属钠" in str(substances)
    assert "氯气" in str(substances)
    assert "一氧化碳" in str(substances)


@pytest.mark.asyncio
async def test_backfill_skips_already_filled(mock_db):
    """回填跳过已有 mode 的题目（查询返回空列表）。"""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    count = await backfill_question_modes(mock_db)
    assert count == 0


def test_chem_session_phase_explicit():
    """化学会话可设置 phase。"""
    s = WenquSession(
        id="WS_TEST",
        student_name="CXY",
        subject="chemistry",
        phase="info_check",
    )
    assert s.phase == "info_check"


def test_physics_session_phase_field_exists():
    """物理会话有 phase 字段但不影响原有逻辑。"""
    s = WenquSession(
        id="WS_TEST",
        student_name="CXY",
        subject="physics",
        phase="info_check",
    )
    assert s.phase == "info_check"
    assert s.subject == "physics"
