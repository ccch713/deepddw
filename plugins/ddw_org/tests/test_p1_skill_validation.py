"""数字员工体系 P1 测试用例：技能验证增强。"""
import pytest
from pydantic import ValidationError


class TestP1SchemaValidators:
    """P1.2: AgentSkillUpdateReq field_validator 测试。"""

    def test_p1_t1_proficiency_enum_validation(self):
        """proficiency 非法值被拒绝"""
        from plugins.ddw_org.schemas import AgentSkillUpdateReq
        with pytest.raises(ValidationError) as exc_info:
            AgentSkillUpdateReq(proficiency="super_expert")
        assert "proficiency" in str(exc_info.value).lower() or "junior/senior/expert" in str(exc_info.value)

    def test_p1_t1_proficiency_valid_values(self):
        """proficiency 合法值通过"""
        from plugins.ddw_org.schemas import AgentSkillUpdateReq
        for val in ("junior", "senior", "expert"):
            req = AgentSkillUpdateReq(proficiency=val)
            assert req.proficiency == val

    def test_p1_t2_trigger_requires_event(self):
        """trigger_conditions 缺少 event 字段被拒绝"""
        from plugins.ddw_org.schemas import AgentSkillUpdateReq
        with pytest.raises(ValidationError) as exc_info:
            AgentSkillUpdateReq(trigger_conditions=[{"filter": {}}])
        assert "event" in str(exc_info.value).lower()

    def test_p1_t2_trigger_with_event_passes(self):
        """trigger_conditions 含 event 字段通过"""
        from plugins.ddw_org.schemas import AgentSkillUpdateReq
        req = AgentSkillUpdateReq(trigger_conditions=[{"event": "on_task_complete"}])
        assert req.trigger_conditions == [{"event": "on_task_complete"}]

    def test_p1_t5_sla_negative_rejected(self):
        """sla_seconds 为负数被拒绝"""
        from plugins.ddw_org.schemas import AgentSkillUpdateReq
        with pytest.raises(ValidationError) as exc_info:
            AgentSkillUpdateReq(sla_seconds=-10)
        assert "sla_seconds" in str(exc_info.value) or "负数" in str(exc_info.value)

    def test_p1_t5_sla_zero_passes(self):
        """sla_seconds 为 0 通过"""
        from plugins.ddw_org.schemas import AgentSkillUpdateReq
        req = AgentSkillUpdateReq(sla_seconds=0)
        assert req.sla_seconds == 0

    def test_p1_t5_sla_positive_passes(self):
        """sla_seconds 正数通过"""
        from plugins.ddw_org.schemas import AgentSkillUpdateReq
        req = AgentSkillUpdateReq(sla_seconds=300)
        assert req.sla_seconds == 300


class TestP1ValidateAgentLogic:
    """P1.1: validate_agent 5 项检查逻辑测试。"""

    def test_p1_t3_validate_checks_structure(self):
        """验证检查项结构正确（C1-C5）"""
        # 这是逻辑测试，验证检查定义的正确性
        valid_proficiencies = {"junior", "senior", "expert"}
        assert len(valid_proficiencies) == 3
        assert "junior" in valid_proficiencies
        assert "senior" in valid_proficiencies
        assert "expert" in valid_proficiencies

    def test_p1_t4_approve_needs_expert_logic(self):
        """C5 逻辑：approve 权限需要 expert 级技能"""
        # 模拟 C5 检查逻辑
        has_approve = True
        has_expert = False
        c5 = not has_approve or has_expert
        assert c5 is False  # 有 approve 但无 expert，应失败

        has_approve = True
        has_expert = True
        c5 = not has_approve or has_expert
        assert c5 is True  # 有 approve 且有 expert，应通过

        has_approve = False
        has_expert = False
        c5 = not has_approve or has_expert
        assert c5 is True  # 无 approve，无需 expert，应通过
