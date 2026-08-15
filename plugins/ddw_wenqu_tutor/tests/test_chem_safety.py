"""M1 安全规则测试。"""
from __future__ import annotations

from plugins.ddw_wenqu_tutor.prompt.chemistry_safety import (
    SAFETY_IRON_RULES, SAFETY_RULES,
)


def test_safety_rules_count():
    """20 条安全规则。"""
    assert len(SAFETY_RULES) == 20


def test_safety_iron_rules_not_empty():
    """铁律非空且含 7 条。"""
    assert len(SAFETY_IRON_RULES) > 100
    # 验证关键铁律内容
    assert "浓硫酸" in SAFETY_IRON_RULES
    assert "金属钠" in SAFETY_IRON_RULES
    assert "氯气" in SAFETY_IRON_RULES
    assert "一氧化碳" in SAFETY_IRON_RULES


def test_safety_rule_fields():
    """每条规则含 4 个必需字段。"""
    for rule in SAFETY_RULES:
        assert "id" in rule
        assert "substance" in rule
        assert "danger_type" in rule
        assert "protection" in rule
        assert "emergency" in rule


def test_safety_rule_concentrated_sulfuric_acid():
    """浓硫酸规则存在且含关键信息。"""
    rule = next(r for r in SAFETY_RULES if r["id"] == 1)
    assert "浓硫酸" in rule["substance"]
    assert "酸入水" in rule["protection"]


def test_safety_rule_sodium():
    """金属钠规则存在。"""
    rule = next(r for r in SAFETY_RULES if r["id"] == 2)
    assert "钠" in rule["substance"]
    assert "禁止用水" in rule["emergency"]


def test_safety_rule_chlorine():
    """氯气规则存在。"""
    rule = next(r for r in SAFETY_RULES if r["id"] == 3)
    assert "氯" in rule["substance"]
    assert "NaOH" in rule["emergency"]


def test_safety_rule_co():
    """CO 规则存在。"""
    rule = next(r for r in SAFETY_RULES if r["id"] == 4)
    assert "一氧化碳" in rule["substance"]
