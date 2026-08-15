"""题库索引 + 评判测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plugins.ddw_wenqu_tutor.models import WenquQuestion
from plugins.ddw_wenqu_tutor.services.questions import (
    get_question,
    judge_answer,
    list_questions,
)


@pytest.fixture
def mock_db():
    """Mock 数据库会话。"""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    # Mock execute 返回正确结构
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar.return_value = 0
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result
    return db


@pytest.fixture
def sample_question():
    """示例题目。"""
    return WenquQuestion(
        id="Q_TEST_001",
        subject="physics",
        chapter="力学",
        year=2025,
        difficulty="medium",
        source="2025 武汉中考",
        question_text="一个物体质量为 2kg，受到 10N 的力，求加速度。",
        answer="5 m/s²",
        explanation="F=ma, a=F/m=10/2=5",
        knowledge_points='["牛顿第二定律", "加速度"]',
    )


@pytest.mark.asyncio
async def test_list_questions(mock_db):
    """题目列表查询。"""
    # Mock 两次 execute 调用（count + select）
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 0

    mock_select_result = MagicMock()
    mock_select_result.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [
        mock_count_result,
        mock_select_result,
    ]

    questions, total = await list_questions(
        mock_db, subject="physics"
    )
    assert questions == []
    assert total == 0


@pytest.mark.asyncio
async def test_get_question(mock_db, sample_question):
    """获取单个题目。"""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = (
        sample_question
    )
    mock_db.execute.return_value = mock_result

    question = await get_question(
        mock_db, "Q_TEST_001"
    )
    assert question is not None
    assert question.id == "Q_TEST_001"


@pytest.mark.asyncio
async def test_judge_correct(
    mock_db, sample_question
):
    """答对了。"""
    with patch(
        "plugins.ddw_wenqu_tutor.services.questions.get_question",
        return_value=sample_question,
    ):
        result = await judge_answer(
            mock_db, "Q_TEST_001", "5 m/s²"
        )

        assert result["correct"] is True
        assert result["error_type"] is None
        assert result["wrong_id"] is None


@pytest.mark.asyncio
async def test_judge_wrong_creates_wrongbook(
    mock_db, sample_question
):
    """答错 → 错题记录 + error_type 分类。"""
    with patch(
        "plugins.ddw_wenqu_tutor.services.questions.get_question",
        return_value=sample_question,
    ):
        result = await judge_answer(
            mock_db, "Q_TEST_001", "10 m/s²"
        )

        assert result["correct"] is False
        assert result["error_type"] in [
            "concept",
            "calculation",
            "unit",
            "misread",
        ]
        assert result["knowledge_gap"] is not None
        assert result["wrong_id"] is not None
        assert result["wrong_id"].startswith("W")

        # 验证错题记录被添加
        assert mock_db.add.called
        assert mock_db.commit.called


@pytest.mark.asyncio
async def test_judge_unit_error(mock_db):
    """单位错误识别。"""
    question = WenquQuestion(
        id="Q_UNIT_001",
        subject="physics",
        chapter="力学",
        year=2025,
        difficulty="easy",
        source="2025 武汉中考",
        question_text="求速度",
        answer="5 m/s",
        knowledge_points='["速度"]',
    )

    with patch(
        "plugins.ddw_wenqu_tutor.services.questions.get_question",
        return_value=question,
    ):
        result = await judge_answer(
            mock_db, "Q_UNIT_001", "5 kg"
        )

        assert result["correct"] is False
        assert result["error_type"] == "unit"


@pytest.mark.asyncio
async def test_judge_question_not_found(mock_db):
    """题目不存在。"""
    with patch(
        "plugins.ddw_wenqu_tutor.services.questions.get_question",
        return_value=None,
    ):
        with pytest.raises(ValueError, match="not found"):
            await judge_answer(
                mock_db, "Q_NOT_EXIST", "test"
            )
