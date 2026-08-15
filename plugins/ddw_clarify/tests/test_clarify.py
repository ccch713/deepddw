"""Tests for Clarify plugin — service + models."""
import os
import sys

import pytest

_project_root = os.path.join(os.path.dirname(__file__), "..", "..")
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from plugins.ddw_clarify.models import ClarifyRule, ClarifySession
from plugins.ddw_clarify.service import ClarifyService


@pytest.fixture
def service():
    return ClarifyService()


# ------------------------------------------------------------------
# 1. 模糊问题触发澄清
# ------------------------------------------------------------------

class TestDetect:
    def test_detect_ambiguous_subject(self, service):
        """包含「这个」的模糊主语应触发澄清。"""
        result = service.detect("这个怎么处理一下")
        assert result["needs_clarification"] is True
        assert result["matched_rule"] is not None
        assert result["session_id"] != ""
        assert result["clarification_round"] == 1

    def test_detect_clear_question(self, service):
        """明确问题不需要澄清。"""
        result = service.detect("请生成2026年8月的质量报告")
        assert result["needs_clarification"] is False
        assert result["matched_rule"] is None

    def test_detect_missing_time_range(self, service):
        """缺少时间范围应触发澄清。"""
        result = service.detect("把最近的数据导出")
        assert result["needs_clarification"] is True
        assert result["matched_rule"].rule_id == "missing_time_range"

    def test_detect_reuses_session(self, service):
        """传入已有 session_id 应复用会话。"""
        r1 = service.detect("这个弄一下")
        sid = r1["session_id"]
        r2 = service.detect("还是那个问题", session_id=sid)
        assert r2["session_id"] == sid


# ------------------------------------------------------------------
# 2. 用户回答 → 确认 / 追问
# ------------------------------------------------------------------

class TestRespond:
    def test_respond_sufficient_answer(self, service):
        """足够详细的回答直接确认。"""
        det = service.detect("那个怎么处理")
        sid = det["session_id"]
        resp = service.respond(sid, "指的是ARA粉剂的批次20260801")
        assert resp["status"] == "confirmed"
        assert resp["confirmed_data"] is not None

    def test_respond_short_answer_triggers_follow_up(self, service):
        """过短回答触发追问。"""
        det = service.detect("这个情况怎么样")
        sid = det["session_id"]
        resp = service.respond(sid, "嗯")
        assert resp["status"] == "clarifying"
        assert resp["next_question"] != ""

    def test_respond_max_rounds_forces_confirm(self, service):
        """达到最大轮次后强制确认。"""
        svc = ClarifyService(max_rounds=2)
        det = svc.detect("这个东西弄一下")
        sid = det["session_id"]
        svc.respond(sid, "嗯")
        resp = svc.respond(sid, "啊")
        assert resp["status"] == "confirmed"
        assert resp["confirmed_data"]["forced"] is True

    def test_respond_unknown_session(self, service):
        """不存在的 session 返回 error。"""
        resp = service.respond("nonexistent_id", "answer")
        assert resp["status"] == "error"


# ------------------------------------------------------------------
# 3. 规则管理
# ------------------------------------------------------------------

class TestRules:
    def test_list_default_rules(self, service):
        """默认规则列表非空且按优先级降序。"""
        rules = service.list_rules()
        assert len(rules) >= 5
        priorities = [r.priority for r in rules]
        assert priorities == sorted(priorities, reverse=True)

    def test_add_and_remove_rule(self, service):
        """自定义规则可增删。"""
        rule = ClarifyRule(
            rule_id="custom_test",
            name="测试规则",
            trigger_condition="测试触发",
            question_template="测试反问？",
            priority=100,
        )
        service.add_rule(rule)
        assert any(r.rule_id == "custom_test" for r in service.list_rules())
        assert service.remove_rule("custom_test") is True
        assert not any(r.rule_id == "custom_test" for r in service.list_rules())


# ------------------------------------------------------------------
# 4. Pydantic 模型基础校验
# ------------------------------------------------------------------

class TestModels:
    def test_clarify_session_defaults(self):
        session = ClarifySession()
        assert session.status == "pending"
        assert session.clarification_round == 0
        assert session.max_rounds == 3
        assert session.session_id != ""

    def test_clarify_rule_roundtrip(self):
        rule = ClarifyRule(
            name="test",
            trigger_condition="foo",
            question_template="bar {subject}?",
        )
        data = rule.model_dump()
        restored = ClarifyRule(**data)
        assert restored.rule_id == rule.rule_id
        assert restored.name == "test"
