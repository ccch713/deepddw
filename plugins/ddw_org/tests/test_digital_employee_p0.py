"""数字员工体系 P0 测试用例。"""
import subprocess


class TestDigitalEmployeeP0:
    """数字员工体系 P0 测试用例。"""

    # T6: roles.py 包含 DIGITAL_AGENT 角色
    def test_t6_digital_agent_role_exists(self):
        """Role.DIGITAL_AGENT 存在且值正确"""
        from core.constants.roles import Role, DIGITAL_ROLES, ALL_ROLES
        assert Role.DIGITAL_AGENT == "digital_agent"
        assert Role.DIGITAL_AGENT in DIGITAL_ROLES
        assert Role.DIGITAL_AGENT in ALL_ROLES

    # T6b: HUMAN_ROLES 不含 DIGITAL_AGENT
    def test_t6b_human_roles_exclude_digital(self):
        """HUMAN_ROLES 不含 DIGITAL_AGENT"""
        from core.constants.roles import Role, HUMAN_ROLES
        assert Role.DIGITAL_AGENT not in HUMAN_ROLES

    # T8: 迁移脚本幂等执行
    def test_t8_migration_idempotent(self):
        """迁移脚本重复执行不报错"""
        result = subprocess.run(
            ["python3", "scripts/migrate_digital_employee_p0.py"],
            capture_output=True,
            text=True,
            cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent.parent),
        )
        assert result.returncode == 0
        assert "跳过" in result.stdout or "已存在" in result.stdout or "迁移完成" in result.stdout

    # T-roles-values: ROLE_VALUES 包含 DIGITAL_AGENT
    def test_t_roles_values_includes_digital_agent(self):
        """ROLE_VALUES 列表包含 DIGITAL_AGENT"""
        from core.constants.roles import Role, ROLE_VALUES
        assert Role.DIGITAL_AGENT in ROLE_VALUES

    # T-all-roles: ALL_ROLES 包含所有角色
    def test_t_all_roles_complete(self):
        """ALL_ROLES 包含人类和数字员工角色"""
        from core.constants.roles import ALL_ROLES, HUMAN_ROLES, DIGITAL_ROLES
        assert ALL_ROLES == HUMAN_ROLES | DIGITAL_ROLES
        assert len(ALL_ROLES) == len(HUMAN_ROLES) + len(DIGITAL_ROLES)

    # T-models-import: 模型可正常导入
    def test_t_models_import(self):
        """ddw_org models 可正常导入且包含新字段"""
        from plugins.ddw_org.models import Department, DigitalAgent, AgentSkill
        # 检查 Department 有 manager_user_id
        assert hasattr(Department, "manager_user_id")
        # 检查 DigitalAgent 有新字段
        assert hasattr(DigitalAgent, "job_objective")
        assert hasattr(DigitalAgent, "report_to")
        assert hasattr(DigitalAgent, "decision_scope")
        assert hasattr(DigitalAgent, "work_boundary")
        # 检查 AgentSkill 有新字段
        assert hasattr(AgentSkill, "proficiency")
        assert hasattr(AgentSkill, "trigger_conditions")
        assert hasattr(AgentSkill, "sla_seconds")

    # T-flow-models: flow_designer 模型可正常导入且包含新字段
    def test_t_flow_models_import(self):
        """ddw_flow_designer models 可正常导入且包含新字段"""
        from plugins.ddw_flow_designer.models import FlowDefinition, FlowReview
        assert hasattr(FlowDefinition, "input_spec")
        assert hasattr(FlowDefinition, "output_spec")
        assert hasattr(FlowDefinition, "cross_dept_review_config")
        assert hasattr(FlowReview, "checklist_results")
        assert hasattr(FlowReview, "skill_merger_approved")
        assert hasattr(FlowReview, "review_deadline")
        assert hasattr(FlowReview, "remind_count")

    # T-schemas: schemas 可正常导入且包含新类
    def test_t_schemas_import(self):
        """ddw_org schemas 可正常导入且包含新类"""
        from plugins.ddw_org.schemas import (
            AgentSkillUpdateReq,
            AgentUpdateReq,
            DepartmentUpdateReq,
        )
        # AgentUpdateReq 包含新字段
        assert "job_objective" in AgentUpdateReq.model_fields
        assert "report_to" in AgentUpdateReq.model_fields
        assert "decision_scope" in AgentUpdateReq.model_fields
        assert "work_boundary" in AgentUpdateReq.model_fields
        # DepartmentUpdateReq 包含 manager_user_id
        assert "manager_user_id" in DepartmentUpdateReq.model_fields
        # AgentSkillUpdateReq 包含新字段
        assert "proficiency" in AgentSkillUpdateReq.model_fields
        assert "trigger_conditions" in AgentSkillUpdateReq.model_fields
        assert "sla_seconds" in AgentSkillUpdateReq.model_fields
