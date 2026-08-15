"""DDW 岗位设计器 - 决策路由引擎测试。"""

from __future__ import annotations

import pytest

from plugins.ddw_position_designer.decision_router import (
    AGENT_RECOMMENDATIONS,
    DEFAULT_DECISION_TYPES,
    DecisionRouter,
    recommend_agents,
    suggest_decision_type,
)


# ===========================================================================
# DecisionRouter
# ===========================================================================


def test_router_weights_sum_to_one():
    """5 因素权重合计 1.0。"""
    total = sum(DecisionRouter.WEIGHTS.values())
    assert abs(total - 1.0) < 0.001


def test_router_recommend_auto():
    """低风险 + 低复杂度 + 高 precedent → auto。"""
    r = DecisionRouter()
    factors = {
        "risk_level": 0.1, "explainability": 0.1, "complexity": 0.1,
        "urgency": 0.5, "precedent": 0.9,
    }
    assert r.recommend(factors) == "auto"


def test_router_recommend_suggest():
    """中等风险 + 中等复杂度 → suggest。"""
    r = DecisionRouter()
    factors = {
        "risk_level": 0.4, "explainability": 0.3, "complexity": 0.4,
        "urgency": 0.5, "precedent": 0.5,
    }
    assert r.recommend(factors) == "suggest"


def test_router_recommend_human():
    """高风险 + 高复杂度 → human。"""
    r = DecisionRouter()
    factors = {
        "risk_level": 0.8, "explainability": 0.6, "complexity": 0.8,
        "urgency": 0.3, "precedent": 0.3,
    }
    assert r.recommend(factors) == "human"


def test_router_recommend_escalate():
    """极高风险 + 极低 precedent → escalate。"""
    r = DecisionRouter()
    factors = {
        "risk_level": 0.95, "explainability": 0.95, "complexity": 0.9,
        "urgency": 0.1, "precedent": 0.05,
    }
    assert r.recommend(factors) == "escalate"


def test_router_explain_returns_rationale():
    """explain 返回 decision + rationale + 各因素贡献。"""
    r = DecisionRouter()
    factors = {
        "risk_level": 0.3, "explainability": 0.3, "complexity": 0.3,
        "urgency": 0.7, "precedent": 0.8,
    }
    result = r.explain(factors)
    assert "decision" in result
    assert "rationale" in result
    assert "factors" in result
    assert "weights" in result
    assert "contributions" in result
    assert result["decision"] in ("auto", "suggest", "human", "escalate")


def test_router_default_factors():
    """未提供某因素时使用默认值 0.5。"""
    r = DecisionRouter()
    # 不传任何因素
    decision = r.recommend({})
    assert decision in ("auto", "suggest", "human", "escalate")


# ===========================================================================
# 场景关键词建议
# ===========================================================================


def test_suggest_decision_type_quote():
    """'报价' → suggest。"""
    assert suggest_decision_type("常规报价") == "suggest"


def test_suggest_decision_type_data_entry():
    """'数据录入' → auto。"""
    assert suggest_decision_type("客户数据录入") == "auto"


def test_suggest_decision_type_contract():
    """'合同签署' → human。"""
    assert suggest_decision_type("合同签署") == "human"


def test_suggest_decision_type_refund():
    """'退款审批' → escalate。"""
    assert suggest_decision_type("退款审批") == "escalate"


def test_suggest_decision_type_unknown_default():
    """未知场景默认 suggest。"""
    assert suggest_decision_type("某种新业务") == "suggest"


def test_suggest_decision_type_empty():
    """空场景默认 suggest。"""
    assert suggest_decision_type("") == "suggest"


# ===========================================================================
# Agent 推荐
# ===========================================================================


def test_recommend_agents_sales():
    """销售部推荐 CRM/数据分析/客服 Agent。"""
    agents = recommend_agents("销售部", limit=5)
    assert "CRM Agent" in agents
    assert "数据分析 Agent" in agents


def test_recommend_agents_cs():
    """客服部推荐在线客服/工单/知识库。"""
    agents = recommend_agents("客服部", limit=5)
    assert "在线客服 Agent" in agents
    assert "知识库 Agent" in agents


def test_recommend_agents_unknown_dept():
    """未知部门返回默认。"""
    agents = recommend_agents("未知部门", limit=3)
    assert len(agents) > 0
    assert all(isinstance(a, str) for a in agents)


def test_recommend_agents_empty_dept():
    """空部门返回默认。"""
    agents = recommend_agents("", limit=3)
    assert len(agents) > 0


def test_all_departments_have_agents():
    """11 部门都应有 Agent 推荐。"""
    for dept in ["销售部", "市场部", "客服部", "生产部", "研发部", "质量部",
                  "采购部", "人力资源部", "财务部", "IT 部", "行政部"]:
        assert dept in AGENT_RECOMMENDATIONS, f"missing dept: {dept}"
        assert len(AGENT_RECOMMENDATIONS[dept]) >= 3


def test_default_decision_types_completeness():
    """默认决策类型映射覆盖核心场景。"""
    required_scenarios = ["报价", "客户投诉", "数据录入", "合同签署", "退款审批"]
    for s in required_scenarios:
        assert s in DEFAULT_DECISION_TYPES
