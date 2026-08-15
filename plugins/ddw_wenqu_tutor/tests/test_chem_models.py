"""M0 模型扩展测试。"""
from __future__ import annotations

from plugins.ddw_wenqu_tutor.models import (
    WenquQuestion, WenquWrongAnswer, WenquSession,
)


def test_question_mode_field_default_none():
    """WenquQuestion.mode 默认 None。"""
    q = WenquQuestion(
        id="Q1", subject="chemistry", chapter="酸碱盐",
        year=2025, difficulty="medium", source="test",
        question_text="test", answer="test",
        knowledge_points='["酸碱盐"]',
    )
    assert q.mode is None


def test_question_is_ai_generated_default_false():
    """WenquQuestion.is_ai_generated 默认 False（flush 后生效）。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from plugins.ddw_wenqu_tutor.models import WenquBase

    q = WenquQuestion(
        id="Q2", subject="chemistry", chapter="氧化还原",
        year=2025, difficulty="hard", source="test",
        question_text="test", answer="test",
        knowledge_points='["氧化还原"]',
    )
    engine = create_engine("sqlite://")
    WenquBase.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(q)
        db.flush()
        assert q.is_ai_generated is False


def test_wrong_answer_four_questions_fields():
    """WenquWrongAnswer 四问字段可赋值。"""
    w = WenquWrongAnswer(
        id="W1", student_name="CXY",
        question_id="Q1", student_answer="错答",
        error_type="concept", knowledge_gap="test",
        correct_parts="第一步写对了",
        error_location="第二步配平",
        error_root_cause="得失电子不守恒",
        check_strategy="下次先标化合价再配平",
        mode="ion_redox",
    )
    assert w.correct_parts == "第一步写对了"
    assert w.error_location == "第二步配平"
    assert w.error_root_cause == "得失电子不守恒"
    assert w.check_strategy == "下次先标化合价再配平"
    assert w.mode == "ion_redox"


def test_wrong_answer_four_fields_nullable():
    """四问字段默认 None（兼容旧数据）。"""
    w = WenquWrongAnswer(
        id="W2", student_name="CXY",
        question_id="Q1", student_answer="错答",
        error_type="concept", knowledge_gap="test",
    )
    assert w.correct_parts is None
    assert w.error_location is None
    assert w.error_root_cause is None
    assert w.check_strategy is None
    assert w.mode is None


def test_session_phase_default_info_check():
    """WenquSession.phase 默认 info_check（flush 后生效）。"""
    from datetime import datetime

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from plugins.ddw_wenqu_tutor.models import WenquBase

    s = WenquSession(
        id="WS_TEST", student_name="CXY",
        subject="chemistry", started_at=datetime.now(),
    )
    engine = create_engine("sqlite://")
    WenquBase.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(s)
        db.flush()
        assert s.phase == "info_check"


def test_session_phase_all_values():
    """phase 枚举值可赋值。"""
    phases = [
        "info_check", "mode_select", "chem_analysis",
        "answer_diag", "pinpoint", "min_intervention",
        "verify_transfer", "record",
    ]
    for p in phases:
        s = WenquSession(
            id=f"WS_{p}", student_name="CXY",
            subject="chemistry", phase=p,
        )
        assert s.phase == p


def test_question_mode_all_enums():
    """11 种模式枚举可赋值。"""
    modes = [
        "substance_change", "ion_redox", "quant_calc",
        "experiment", "test_identify", "purify_separate",
        "chart_table", "process_flow", "electrochem",
        "structure", "organic",
    ]
    for m in modes:
        q = WenquQuestion(
            id=f"Q_{m}", subject="chemistry",
            chapter="test", year=2025,
            difficulty="medium", source="test",
            question_text="test", answer="test",
            knowledge_points='[]', mode=m,
        )
        assert q.mode == m
