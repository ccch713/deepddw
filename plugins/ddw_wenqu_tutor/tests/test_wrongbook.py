"""错题归档 + 复盘生成测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from plugins.ddw_wenqu_tutor.models import WenquWrongAnswer
from plugins.ddw_wenqu_tutor.services.wrongbook import (
    build_redo_prompt,
    get_wrong_answer,
    list_wrong_answers,
    mark_resolved,
    start_redo_session,
)


@pytest.fixture
def mock_db():
    """Mock 数据库会话。"""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def sample_wrong():
    """示例错题。"""
    return WenquWrongAnswer(
        id="W_TEST_001",
        student_name="CXY",
        question_id="Q_TEST_001",
        session_id="WS_TEST_001",
        student_answer="10 m/s²",
        error_type="calculation",
        knowledge_gap="牛顿第二定律",
        resolved=False,
    )


@pytest.mark.asyncio
async def test_list_wrong_answers(mock_db):
    """错题列表查询。"""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    wrongs = await list_wrong_answers(
        mock_db, student_name="CXY"
    )
    assert wrongs == []


@pytest.mark.asyncio
async def test_list_wrong_answers_resolved_filter(
    mock_db,
):
    """按 resolved 过滤。"""
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    await list_wrong_answers(
        mock_db, student_name="CXY", resolved=False
    )
    # 验证查询被执行
    assert mock_db.execute.called


@pytest.mark.asyncio
async def test_get_wrong_answer(mock_db, sample_wrong):
    """获取单个错题。"""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = (
        sample_wrong
    )
    mock_db.execute.return_value = mock_result

    wrong = await get_wrong_answer(
        mock_db, "W_TEST_001"
    )
    assert wrong is not None
    assert wrong.id == "W_TEST_001"


@pytest.mark.asyncio
async def test_mark_resolved(mock_db):
    """标记已解决。"""
    result = await mark_resolved(mock_db, "W_TEST_001")
    assert result is True
    assert mock_db.commit.called


def test_build_redo_prompt(sample_wrong):
    """复盘 prompt 含知识缺口入口。"""
    prompt = build_redo_prompt(sample_wrong)
    assert "Q_TEST_001" in prompt
    assert "10 m/s²" in prompt
    assert "calculation" in prompt
    assert "牛顿第二定律" in prompt
    assert "苏格拉底" in prompt
    assert "审题" in prompt


@pytest.mark.asyncio
async def test_start_redo_session(
    mock_db, sample_wrong
):
    """开始复盘会话。"""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = (
        sample_wrong
    )
    mock_db.execute.return_value = mock_result

    result = await start_redo_session(
        mock_db, "W_TEST_001"
    )

    assert "session_id" in result
    assert result["session_id"].startswith("WS_REDO_")
    assert "first_question" in result
    assert "redo_prompt" in result
    assert "题目" in result["first_question"]


@pytest.mark.asyncio
async def test_start_redo_session_not_found(mock_db):
    """错题不存在。"""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    with pytest.raises(ValueError, match="not found"):
        await start_redo_session(
            mock_db, "W_NOT_EXIST"
        )
