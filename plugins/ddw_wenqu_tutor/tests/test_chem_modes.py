"""M1 模式识别测试。"""
from __future__ import annotations

from plugins.ddw_wenqu_tutor.prompt.chem_modes import (
    CHEM_MODES, MODE_KEYS, identify_mode,
    build_mode_card_prompt,
)


def test_chem_modes_count():
    """11 个模式全部注册。"""
    assert len(CHEM_MODES) == 11
    assert len(MODE_KEYS) == 11


def test_identify_ion_redox():
    """含"氧化还原"→ ion_redox。"""
    mode = identify_mode(
        "判断下列反应是否为氧化还原反应",
        '["氧化还原"]',
    )
    assert mode == "ion_redox"


def test_identify_quant_calc():
    """含"质量""计算"→ quant_calc。"""
    mode = identify_mode(
        "计算反应生成物的质量",
    )
    assert mode == "quant_calc"


def test_identify_experiment():
    """含"实验""装置"→ experiment。"""
    mode = identify_mode(
        "画出实验室制取氧气的装置图",
    )
    assert mode == "experiment"


def test_identify_organic():
    """含"有机""官能团"→ organic。"""
    mode = identify_mode(
        "判断下列有机物的官能团",
    )
    assert mode == "organic"


def test_identify_no_match():
    """无关键词匹配返回 None。"""
    mode = identify_mode("这是一道数学题")
    assert mode is None


def test_build_mode_card_prompt():
    """卡片 prompt 含关键字段。"""
    prompt = build_mode_card_prompt("ion_redox")
    assert "离子反应与氧化还原" in prompt
    assert "处理顺序" in prompt
    assert "易错点" in prompt
    assert "升失氧还" in prompt


def test_build_mode_card_prompt_unknown():
    """未知模式返回空字符串。"""
    prompt = build_mode_card_prompt("nonexistent")
    assert prompt == ""
