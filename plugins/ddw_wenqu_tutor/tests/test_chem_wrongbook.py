"""M4 四问+redo 测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from plugins.ddw_wenqu_tutor.models import WenquWrongAnswer
from plugins.ddw_wenqu_tutor.services.wrongbook import (
    build_redo_prompt,
    get_four_questions,
    start_redo_session,
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def wrong_with_four_questions():
    return WenquWrongAnswer(
        id="W_CHEM_001",
        student_name="CXY",
        question_id="Q_CHEM_001",
        session_id="WS_TEST",
        student_answer="不是氧化还原",
        error_type="valence",
        knowledge_gap="氧化还原",
        correct_parts="正确识别了这是置换反应",
        error_location="Fe 的化合价标注",
        error_root_cause="误认为 Fe 在化合物中也是 0 价",
        check_strategy="单质中元素化合价为 0",
        mode="ion_redox",
        resolved=False,
    )


@pytest.fixture
def wrong_without_four_questions():
    return WenquWrongAnswer(
        id="W_OLD_001",
        student_name="CXY",
        question_id="Q_OLD_001",
        student_answer="错答",
        error_type="concept",
        knowledge_gap="test",
        resolved=False,
    )


@pytest.mark.asyncio
async def test_get_four_questions(
    mock_db, wrong_with_four_questions
):
    """获取四问详情。"""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = (
        wrong_with_four_questions
    )
    mock_db.execute.return_value = mock_result

    result = await get_four_questions(mock_db, "W_CHEM_001")
    assert result is not None
    assert result["wrong_id"] == "W_CHEM_001"
    assert result["mode"] == "ion_redox"
    assert "Fe" in result["four_questions"]["error_location"]


@pytest.mark.asyncio
async def test_get_four_questions_not_found(mock_db):
    """四问：错题不存在返回 None。"""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    result = await get_four_questions(mock_db, "W_NOT_EXIST")
    assert result is None


def test_build_redo_prompt_with_four_questions(
    wrong_with_four_questions,
):
    """redo prompt 含四问卡片。"""
    prompt = build_redo_prompt(wrong_with_four_questions)
    assert "错题四问卡片" in prompt
    assert "做对了什么" in prompt
    assert "错在哪儿" in prompt
    assert "为什么错" in prompt
    assert "下次怎么检查" in prompt


def test_build_redo_prompt_without_four_questions(
    wrong_without_four_questions,
):
    """旧数据无四问时 prompt 仍正常。"""
    prompt = build_redo_prompt(wrong_without_four_questions)
    assert "苏格拉底复盘" in prompt
    assert "错题四问卡片" not in prompt


@pytest.mark.asyncio
async def test_start_redo_session_with_four_questions(
    mock_db, wrong_with_four_questions
):
    """redo 会话含四问卡片。"""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = (
        wrong_with_four_questions
    )
    mock_db.execute.return_value = mock_result

    result = await start_redo_session(mock_db, "W_CHEM_001")
    assert result["four_questions"] is not None
    assert "Fe" in result["first_question"]
    assert result["session_id"].startswith("WS_REDO_")


@pytest.mark.asyncio
async def test_start_redo_session_old_data(
    mock_db, wrong_without_four_questions
):
    """旧数据 redo 会话不含四问。"""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = (
        wrong_without_four_questions
    )
    mock_db.execute.return_value = mock_result

    result = await start_redo_session(mock_db, "W_OLD_001")
    assert result["four_questions"] is None
