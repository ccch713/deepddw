"""M3 化学评判+变式测试。"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plugins.ddw_wenqu_tutor.models import WenquQuestion
from plugins.ddw_wenqu_tutor.services.questions import (
    _map_error_type,
    generate_variant,
    judge_answer,
)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalar.return_value = 0
    mock_result.scalars.return_value.all.return_value = []
    db.execute.return_value = mock_result
    return db


@pytest.fixture
def chem_question():
    return WenquQuestion(
        id="Q_CHEM_001",
        subject="chemistry",
        chapter="氧化还原",
        year=2025,
        difficulty="medium",
        source="2025中考",
        question_text="判断 Fe + CuSO₄ → FeSO₄ + Cu 是否为氧化还原反应",
        answer="是，Fe 化合价从 0 升高到 +2，Cu 从 +2 降低到 0",
        knowledge_points='["氧化还原", "化合价"]',
    )


@pytest.fixture
def mock_llm_correct():
    mock = AsyncMock()
    mock.generate = AsyncMock(
        return_value=json.dumps(
            {
                "correct": True,
                "error_type": None,
                "correct_parts": "全部正确",
                "error_location": "",
                "error_root_cause": "",
                "check_strategy": "",
            },
            ensure_ascii=False,
        )
    )
    return mock


@pytest.fixture
def mock_llm_wrong():
    mock = AsyncMock()
    mock.generate = AsyncMock(
        return_value=json.dumps(
            {
                "correct": False,
                "error_type": "化合价错误",
                "correct_parts": "正确识别了这是置换反应",
                "error_location": "Fe 的化合价标注",
                "error_root_cause": "误认为 Fe 在化合物中也是 0 价",
                "check_strategy": "单质中元素化合价为 0，化合物中需根据其他元素推算",
            },
            ensure_ascii=False,
        )
    )
    return mock


@pytest.mark.asyncio
async def test_judge_chem_correct(
    mock_db, chem_question, mock_llm_correct
):
    """化学题答对。"""
    with patch(
        "plugins.ddw_wenqu_tutor.services.questions.get_question",
        return_value=chem_question,
    ):
        result = await judge_answer(
            mock_db,
            "Q_CHEM_001",
            "是氧化还原反应，Fe 升高 Cu 降低",
            llm_client=mock_llm_correct,
        )
        assert result["correct"] is True
        assert result["wrong_id"] is None
        assert result["mode"] == "ion_redox"


@pytest.mark.asyncio
async def test_judge_chem_wrong_creates_four_questions(
    mock_db, chem_question, mock_llm_wrong
):
    """化学题答错→四问字段。"""
    with patch(
        "plugins.ddw_wenqu_tutor.services.questions.get_question",
        return_value=chem_question,
    ):
        result = await judge_answer(
            mock_db,
            "Q_CHEM_001",
            "不是氧化还原反应",
            llm_client=mock_llm_wrong,
        )
        assert result["correct"] is False
        assert result["error_type"] == "valence"
        assert result["four_questions"] is not None
        assert "Fe" in result["four_questions"]["error_location"]
        assert result["wrong_id"] is not None
        assert result["mode"] == "ion_redox"


@pytest.mark.asyncio
async def test_judge_physics_unchanged(mock_db):
    """物理题走原逻辑不变。"""
    physics_q = WenquQuestion(
        id="Q_PHY_001",
        subject="physics",
        chapter="力学",
        year=2025,
        difficulty="medium",
        source="test",
        question_text="求加速度",
        answer="5 m/s²",
        knowledge_points='["牛顿第二定律"]',
    )
    with patch(
        "plugins.ddw_wenqu_tutor.services.questions.get_question",
        return_value=physics_q,
    ):
        result = await judge_answer(
            mock_db, "Q_PHY_001", "5 m/s²"
        )
        assert result["correct"] is True
        assert result["four_questions"] is None
        assert result["mode"] is None


def test_map_error_type():
    """错误类型映射。"""
    assert _map_error_type("化合价错误") == "valence"
    assert _map_error_type("守恒不守恒") == "conservation_fail"
    assert _map_error_type("方程式错误") == "wrong_reaction"
    assert _map_error_type(None) == "concept"
    assert _map_error_type("unknown") == "unknown"


@pytest.mark.asyncio
async def test_generate_variant(mock_db, chem_question):
    """生成变式题。"""
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(
        return_value=json.dumps(
            {
                "question_text": "判断 2Na + 2H₂O → 2NaOH + H₂↑ 是否为氧化还原反应",
                "answer": "是，Na 从 0 升高到 +1，H 从 +1 降低到 0",
                "explanation": "有化合价变化的反应就是氧化还原反应",
                "knowledge_points": ["氧化还原", "化合价"],
            },
            ensure_ascii=False,
        )
    )

    with patch(
        "plugins.ddw_wenqu_tutor.services.questions.get_question",
        return_value=chem_question,
    ):
        result = await generate_variant(
            mock_db, "Q_CHEM_001", "medium", mock_llm
        )
        assert result["is_ai_generated"] is True
        assert result["mode"] == "ion_redox"
        assert "Na" in result["question_text"]
        assert mock_db.add.called
        assert mock_db.commit.called


@pytest.mark.asyncio
async def test_generate_variant_question_not_found(
    mock_db,
):
    """变式题：题目不存在。"""
    with patch(
        "plugins.ddw_wenqu_tutor.services.questions.get_question",
        return_value=None,
    ):
        with pytest.raises(ValueError, match="not found"):
            await generate_variant(mock_db, "Q_NOT_EXIST")
