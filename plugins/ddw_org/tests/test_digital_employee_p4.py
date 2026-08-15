"""数字员工体系 P4 测试用例 — DigitalAgentTemplate + 5 道自动检查。"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from plugins.ddw_org.models import (
    Department,
    DigitalAgent,
    DigitalAgentTemplate,
)


def _make_template(**kwargs):
    """构造 DigitalAgentTemplate mock 对象。"""
    defaults = {
        "id": 1,
        "tenant_id": 1,
        "template_name": "测试模板",
        "template_type": "employee_created",
        "created_by": 1,
        "department_id": 1,
        "agent_name": "测试助手",
        "job_objective": "处理测试任务",
        "role": "测试员",
        "decision_scope": ["read"],
        "work_boundary": "仅执行测试",
        "skills": [{"skill_key": "ddw.llm.chat", "proficiency": "expert"}],
        "input_spec": None,
        "output_spec": None,
        "status": "draft",
        "validation_results": None,
        "approval_status": "pending",
        "approved_by": None,
        "approved_at": None,
    }
    defaults.update(kwargs)
    return MagicMock(**defaults)


def _make_dept(**kwargs):
    """构造 Department mock 对象。"""
    defaults = {"id": 1, "tenant_id": 1, "name": "技术部"}
    defaults.update(kwargs)
    return MagicMock(**defaults)


def _make_skill_pool(skill_key="ddw.llm.chat", tenant_id=1):
    """构造 OrgSkillPool mock 对象。"""
    return MagicMock(skill_key=skill_key, tenant_id=tenant_id)


class TestTemplateP4:
    """P4: DigitalAgentTemplate + 5 道自动检查。"""

    # T1: 创建模板 → status=draft
    @pytest.mark.asyncio
    async def test_create_template_status_draft(self):
        """创建模板后 status=draft。"""
        from plugins.ddw_org.services.template_service import TemplateService

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        svc = TemplateService(mock_db)
        data = {
            "template_name": "测试模板",
            "department_id": 1,
            "agent_name": "测试助手",
            "role": "测试员",
            "job_objective": "处理测试任务",
            "work_boundary": "仅执行测试",
            "skills": [{"skill_key": "ddw.llm.chat"}],
        }
        # 模拟 refresh 后的对象
        tpl_mock = _make_template(**data)
        tpl_mock.status = "draft"
        mock_db.refresh = AsyncMock(side_effect=lambda t: setattr(t, "status", "draft") or None)

        await svc.create_template(tenant_id=1, created_by=1, data=data)
        assert mock_db.add.called
        assert mock_db.commit.called

    # T2: 5 道检查全部通过 → status=validation_passed
    @pytest.mark.asyncio
    async def test_validate_all_passed(self):
        """5 道检查全部通过 → status=validation_passed。"""
        from plugins.ddw_org.services.template_service import TemplateService

        tpl = _make_template(
            skills=[{"skill_key": "ddw.llm.chat", "proficiency": "expert"}],
            decision_scope=["read"],
        )
        dept = _make_dept()
        skill_pool = _make_skill_pool()

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(side_effect=lambda model, id: {
            DigitalAgentTemplate: tpl,
            Department: dept,
        }.get(model))
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[skill_pool])))
        ))
        mock_db.commit = AsyncMock()

        svc = TemplateService(mock_db)
        result = await svc.validate_template(1, 1)

        assert result is not None
        assert result["passed"] is True
        assert len(result["results"]) == 5
        assert all(r["passed"] for r in result["results"])
        assert tpl.status == "validation_passed"

    # T3: 缺少 agent_name → C1 失败
    @pytest.mark.asyncio
    async def test_validate_c1_missing_agent_name(self):
        """缺少 agent_name → C1 字段完整性失败。"""
        from plugins.ddw_org.services.template_service import TemplateService

        tpl = _make_template(agent_name="", job_objective="目标", role="角色",
                            work_boundary="边界", skills=[{"skill_key": "ddw.llm.chat"}])
        dept = _make_dept()
        skill_pool = _make_skill_pool()

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(side_effect=lambda model, id: {
            DigitalAgentTemplate: tpl,
            Department: dept,
        }.get(model))
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[skill_pool])))
        ))
        mock_db.commit = AsyncMock()

        svc = TemplateService(mock_db)
        result = await svc.validate_template(1, 1)

        assert result["passed"] is False
        c1 = next(r for r in result["results"] if r["check"] == "C1")
        assert c1["passed"] is False
        assert "agent_name" in c1["message"]

    # T4: 未注册技能 → C3 失败
    @pytest.mark.asyncio
    async def test_validate_c3_unregistered_skill(self):
        """未注册技能 → C3 技能有效性失败。"""
        from plugins.ddw_org.services.template_service import TemplateService

        tpl = _make_template(skills=[{"skill_key": "ddw.unknown.skill"}])
        dept = _make_dept()

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(side_effect=lambda model, id: {
            DigitalAgentTemplate: tpl,
            Department: dept,
        }.get(model))
        mock_db.execute = AsyncMock(return_value=MagicMock(
            scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        ))
        mock_db.commit = AsyncMock()

        svc = TemplateService(mock_db)
        result = await svc.validate_template(1, 1)

        assert result["passed"] is False
        c3 = next(r for r in result["results"] if r["check"] == "C3")
        assert c3["passed"] is False
        assert "ddw.unknown.skill" in c3["message"]

    # T5: 审批通过 → 创建 DigitalAgent
    @pytest.mark.asyncio
    async def test_approve_creates_agent(self):
        """审批通过 → 创建 DigitalAgent。"""
        from plugins.ddw_org.services.template_service import TemplateService

        tpl = _make_template(
            status="pending_department_approval",
            skills=[{"skill_key": "ddw.llm.chat", "proficiency": "expert"}],
        )

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=tpl)
        mock_db.add = MagicMock()
        mock_db.commit = AsyncMock()

        # 模拟 refresh agent
        async def mock_refresh(obj):
            if isinstance(obj, DigitalAgent) or (hasattr(obj, '__tablename__') and obj.__tablename__ == 'org_digital_agents'):
                obj.id = 42

        mock_db.refresh = mock_refresh

        svc = TemplateService(mock_db)
        result = await svc.approve_template(1, 1, approved_by=2)

        assert result is not None
        assert result["status"] == "created"
        assert result["template_id"] == 1
        assert tpl.status == "active"
        assert tpl.approval_status == "approved"
        assert tpl.approved_by == 2

    # T6: 审批拒绝 → 退回 draft
    @pytest.mark.asyncio
    async def test_reject_returns_to_draft(self):
        """审批拒绝 → 退回 draft。"""
        from plugins.ddw_org.services.template_service import TemplateService

        tpl = _make_template(status="pending_department_approval")

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=tpl)
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        svc = TemplateService(mock_db)
        result = await svc.reject_template(1, 1)

        assert result is not None
        assert tpl.status == "draft"
        assert tpl.approval_status == "rejected"


class TestTemplateModel:
    """DigitalAgentTemplate 模型导入测试。"""

    def test_model_import(self):
        """DigitalAgentTemplate 可正常导入。"""
        from plugins.ddw_org.models import DigitalAgentTemplate
        assert hasattr(DigitalAgentTemplate, "template_name")
        assert hasattr(DigitalAgentTemplate, "agent_name")
        assert hasattr(DigitalAgentTemplate, "skills")
        assert hasattr(DigitalAgentTemplate, "status")
        assert hasattr(DigitalAgentTemplate, "validation_results")
        assert hasattr(DigitalAgentTemplate, "approval_status")

    def test_model_in_all(self):
        """DigitalAgentTemplate 在 __all__ 中。"""
        from plugins.ddw_org import models
        assert "DigitalAgentTemplate" in models.__all__
