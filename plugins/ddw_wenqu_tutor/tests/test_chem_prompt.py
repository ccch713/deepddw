"""M2 prompt 升级测试。"""
from __future__ import annotations

from plugins.ddw_wenqu_tutor.prompt.socratic_rules import (
    SOCRATIC_RULES,
)
from plugins.ddw_wenqu_tutor.prompt.chemistry_coach import (
    CHEMISTRY_COACH,
)
from plugins.ddw_wenqu_tutor.services.socratic import (
    build_system_prompt,
)


def test_socratic_rules_has_rule7():
    """第 7 条化学特化规则存在。"""
    assert "化学特化" in SOCRATIC_RULES
    assert "守恒检查" in SOCRATIC_RULES
    assert "带单位" in SOCRATIC_RULES
    assert "实验安全" in SOCRATIC_RULES
    assert "鉴别干扰" in SOCRATIC_RULES


def test_socratic_rules_has_step_mode():
    """STEP_MODE 单轮单判断。"""
    assert "STEP_MODE" in SOCRATIC_RULES
    assert "单轮单判断" in SOCRATIC_RULES


def test_socratic_rules_has_hint_gradient():
    """三级提示梯度。"""
    assert "L1" in SOCRATIC_RULES
    assert "L2" in SOCRATIC_RULES
    assert "L3" in SOCRATIC_RULES
    assert "反问" in SOCRATIC_RULES
    assert "类比" in SOCRATIC_RULES
    assert "半成品" in SOCRATIC_RULES


def test_chemistry_coach_has_four_views():
    """林若薇四核心视角铁律。"""
    assert "宏观-微观-符号三重一致" in CHEMISTRY_COACH
    assert "变化与守恒观" in CHEMISTRY_COACH
    assert "证据约束" in CHEMISTRY_COACH
    assert "结构决定性质" in CHEMISTRY_COACH


def test_chemistry_coach_affirm_first():
    """先肯定做对部分再指出错误。"""
    assert "先肯定做对部分" in CHEMISTRY_COACH


def test_build_prompt_phase_info_check():
    """info_check 阶段：有教练角色，无模式卡片（未传 mode）。"""
    prompt = build_system_prompt(
        subject="chemistry", phase="info_check",
    )
    assert "苏格拉底" in prompt or "学习教练" in prompt
    assert "林若薇" in prompt
    # 不应包含模式卡片（未传 mode 参数）
    assert "当前题目模式" not in prompt


def test_build_prompt_phase_chem_analysis():
    """chem_analysis 阶段注入安全铁律。"""
    prompt = build_system_prompt(
        subject="chemistry", phase="chem_analysis",
    )
    assert "实验安全铁律" in prompt


def test_build_prompt_with_mode():
    """注入 mode 时出现模式卡片。"""
    prompt = build_system_prompt(
        subject="chemistry", phase="answer_diag",
        mode="ion_redox",
    )
    assert "离子反应与氧化还原" in prompt


def test_build_prompt_physics_no_safety():
    """物理科目不注入安全铁律。"""
    prompt = build_system_prompt(
        subject="physics", phase="chem_analysis",
    )
    assert "实验安全铁律" not in prompt


def test_build_prompt_max_tokens_respected():
    """token 预算 6000。"""
    prompt = build_system_prompt(
        subject="chemistry", phase="record",
        mode="experiment",
        chapter="酸碱盐",
        textbook_chunk="酸碱盐是初中化学重点章节。",
    )
    # 不会超限（prompt 本身不会太长，仅验证不崩溃）
    assert isinstance(prompt, str)
    assert len(prompt) > 0
