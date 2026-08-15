"""科目注册表完整性测试（加科目后自动校验数据齐全）。"""

from __future__ import annotations

from plugins.ddw_wenqu_tutor.prompt.subject_meta import (
    SUBJECT_IDS,
    SUBJECT_NAMES,
    SUBJECTS,
)
from plugins.ddw_wenqu_tutor.schemas import SessionStart


def test_seven_subjects_registered():
    """问渠 7 科齐全（用户拍板：语文/数学/英语/物理/化学/道法/历史）。"""
    assert set(SUBJECT_IDS) == {
        "chinese", "math", "english",
        "physics", "chemistry",
        "morality", "history",
    }


def test_subject_names_chinese():
    assert SUBJECT_NAMES == {
        "chinese": "语文", "math": "数学", "english": "英语",
        "physics": "物理", "chemistry": "化学",
        "morality": "道法", "history": "历史",
    }


def test_every_subject_has_full_meta():
    """每科必须有中文名 + 教练角色 + 变式角色；judge_role 仅物理/化学可空（走专门判断器）。"""
    for sid in SUBJECT_IDS:
        meta = SUBJECTS[sid]
        assert meta["name"], sid
        assert meta["coach"] and len(meta["coach"]) > 20, sid
        assert meta["variant_role"], sid
        if sid in ("physics", "chemistry"):
            assert meta["judge_role"] is None, sid
        else:
            assert meta["judge_role"], sid


def test_session_start_accepts_all_subjects():
    """开课接口接受 7 科任意一科。"""
    for sid in SUBJECT_IDS:
        req = SessionStart(**{
            "student_name": "CXY", "subject": sid, "chapter": "测试章节",
        })
        assert req.subject == sid


def test_new_subject_rejected():
    """未注册科目应被拒绝（Literal 校验）。"""
    import pytest

    with pytest.raises(Exception):
        SessionStart(**{
            "student_name": "CXY", "subject": "biology",
        })
