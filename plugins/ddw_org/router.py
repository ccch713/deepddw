"""DDW AI 组织插件 API 路由。"""
from __future__ import annotations

from typing import Optional

import logging

from fastapi import APIRouter, HTTPException, Query

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter, get_tenant_context

from .schemas import (
    AgentDetailResp,
    AgentResp,
    AgentSkillUpdateReq,
    AgentUpdateReq,
    DepartmentCreateReq,
    DepartmentDetailResp,
    DepartmentResp,
    DepartmentUpdateReq,
    DigitalAgentJobCard,
    EmployeeCreateReq,
    EmployeeResp,
    EmployeeUpdateReq,
    SeedResp,
    SkillAssignReq,
    TemplateCreateReq,
    TemplateResp,
)
from .services.org_service import OrgService
from .services.seed import seed_org_for_tenant
from .services.skill_service import AgentSkillService
from .services.template_service import TemplateService

logger = logging.getLogger(__name__)


def build_router() -> APIRouter:
    """构造 AI 组织路由。"""
    router = APIRouter(prefix="/api/v1/org", tags=["ddw-org"])

    # ── 健康检查 ────────────────────────────────────────────────────────

    @router.get("/health")
    async def health() -> dict:
        return {"plugin": "ddw-org", "version": "1.0.0", "status": "ok"}

    # ── 种子 ────────────────────────────────────────────────────────────

    @router.post("/seed", response_model=SeedResp)
    async def seed() -> SeedResp:
        """手动触发种子数据创建（幂等）。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set in context")
        async with session_scope() as db, bypass_tenant_filter():
            result = await seed_org_for_tenant(db, tenant_id)
            return SeedResp(**result)

    # ── 部门 ────────────────────────────────────────────────────────────

    @router.get("/departments", response_model=list)
    async def list_departments() -> list:
        """部门列表。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = OrgService(db)
            return await svc.list_departments(tenant_id)

    @router.get("/departments/{dept_id}", response_model=DepartmentDetailResp)
    async def get_department(dept_id: int) -> DepartmentDetailResp:
        """部门详情。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = OrgService(db)
            result = await svc.get_department(dept_id, tenant_id)
            if not result:
                raise HTTPException(status_code=404, detail="department not found")
            return DepartmentDetailResp(**result)

    @router.put("/departments/{dept_id}", response_model=DepartmentResp)
    async def update_department(dept_id: int, data: DepartmentUpdateReq) -> DepartmentResp:
        """修改部门。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = OrgService(db)
            result = await svc.update_department(dept_id, tenant_id, data.model_dump(exclude_unset=True))
            if not result:
                raise HTTPException(status_code=404, detail="department not found")
            return DepartmentResp(**result)

    @router.patch("/departments/{dept_id}", response_model=DepartmentResp)
    async def patch_department(dept_id: int, data: DepartmentUpdateReq) -> DepartmentResp:
        """修改部门（PATCH 语义）。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = OrgService(db)
            result = await svc.update_department(dept_id, tenant_id, data.model_dump(exclude_unset=True))
            if not result:
                raise HTTPException(status_code=404, detail="department not found")
            return DepartmentResp(**result)

    @router.get("/departments/{dept_id}/manager", response_model=dict)
    async def get_department_manager(dept_id: int) -> dict:
        """获取部门负责人信息。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = OrgService(db)
            result = await svc.get_department_manager(dept_id, tenant_id)
            if result is None:
                raise HTTPException(status_code=404, detail="manager not assigned")
            return result

    @router.post("/departments", response_model=DepartmentResp, status_code=201)
    async def create_department(data: DepartmentCreateReq) -> DepartmentResp:
        """新建部门。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = OrgService(db)
            result = await svc.create_department(tenant_id, data.model_dump())
            return DepartmentResp(**result)

    # ── 数字员工 ────────────────────────────────────────────────────────

    @router.get("/agents", response_model=list)
    async def list_agents(
        department_id: Optional[int] = Query(None, description="按部门筛选"),
    ) -> list:
        """数字员工列表。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = OrgService(db)
            return await svc.list_agents(tenant_id, department_id)

    @router.get("/agents/{agent_id}", response_model=AgentDetailResp)
    async def get_agent(agent_id: int) -> AgentDetailResp:
        """数字员工详情。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = OrgService(db)
            result = await svc.get_agent(agent_id, tenant_id)
            if not result:
                raise HTTPException(status_code=404, detail="agent not found")
            return AgentDetailResp(**result)

    @router.put("/agents/{agent_id}", response_model=AgentResp)
    async def update_agent(agent_id: int, data: AgentUpdateReq) -> AgentResp:
        """修改数字员工。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = OrgService(db)
            result = await svc.update_agent(agent_id, tenant_id, data.model_dump(exclude_unset=True))
            if not result:
                raise HTTPException(status_code=404, detail="agent not found")
            return AgentResp(**result)

    @router.patch("/agents/{agent_id}", response_model=AgentResp)
    async def patch_agent(agent_id: int, data: AgentUpdateReq) -> AgentResp:
        """修改数字员工（PATCH 语义，含新字段校验）。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        update_data = data.model_dump(exclude_unset=True)
        # job_objective 和 work_boundary 不允许为空字符串
        if "job_objective" in update_data and update_data["job_objective"] == "":
            raise HTTPException(status_code=400, detail="job_objective cannot be empty")
        if "work_boundary" in update_data and update_data["work_boundary"] == "":
            raise HTTPException(status_code=400, detail="work_boundary cannot be empty")
        async with session_scope() as db, bypass_tenant_filter():
            svc = OrgService(db)
            result = await svc.update_agent(agent_id, tenant_id, update_data)
            if not result:
                raise HTTPException(status_code=404, detail="agent not found")
            return AgentResp(**result)

    @router.get("/agents/{agent_id}/job-card", response_model=DigitalAgentJobCard)
    async def get_agent_job_card(agent_id: int) -> DigitalAgentJobCard:
        """获取数字员工完整岗位卡。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = OrgService(db)
            result = await svc.get_agent_job_card(agent_id, tenant_id)
            if not result:
                raise HTTPException(status_code=404, detail="agent not found")
            return DigitalAgentJobCard(**result)

    @router.post("/agents/{agent_id}/validate", response_model=dict)
    async def validate_agent(agent_id: int) -> dict:
        """手动触发数字员工能力验证。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = OrgService(db)
            result = await svc.validate_agent(agent_id, tenant_id)
            if result is None:
                raise HTTPException(status_code=404, detail="agent not found")
            return result

    # ── Skill 分配 ──────────────────────────────────────────────────────

    @router.post("/agents/{agent_id}/skills", response_model=dict, status_code=201)
    async def assign_skill(agent_id: int, data: SkillAssignReq) -> dict:
        """为数字员工分配 skill。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = AgentSkillService(db)
            try:
                return await svc.assign_skill(agent_id, data.skill_id)
            except ValueError as e:
                raise HTTPException(status_code=409, detail=str(e))

    @router.delete("/agents/{agent_id}/skills/{skill_id}", response_model=dict)
    async def remove_skill(agent_id: int, skill_id: int) -> dict:
        """移除数字员工的 skill。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = AgentSkillService(db)
            removed = await svc.remove_skill(agent_id, skill_id)
            if not removed:
                raise HTTPException(status_code=404, detail="skill assignment not found")
            return {"removed": True}

    @router.patch("/agent-skills/{askill_id}", response_model=dict)
    async def patch_agent_skill(askill_id: int, data: AgentSkillUpdateReq) -> dict:
        """更新 agent-skill 关联（proficiency/trigger_conditions/sla_seconds）。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = AgentSkillService(db)
            result = await svc.update_agent_skill(askill_id, data.model_dump(exclude_unset=True))
            if not result:
                raise HTTPException(status_code=404, detail="agent skill not found")
            return result

    # ── 员工 ────────────────────────────────────────────────────────────

    @router.get("/employees", response_model=list)
    async def list_employees(
        department_id: Optional[int] = Query(None, description="按部门筛选"),
    ) -> list:
        """员工列表。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = OrgService(db)
            return await svc.list_employees(tenant_id, department_id)

    @router.post("/employees", response_model=EmployeeResp, status_code=201)
    async def create_employee(data: EmployeeCreateReq) -> EmployeeResp:
        """新增员工。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = OrgService(db)
            result = await svc.create_employee(tenant_id, data.model_dump())
            return EmployeeResp(**result)

    @router.put("/employees/{emp_id}", response_model=EmployeeResp)
    async def update_employee(emp_id: int, data: EmployeeUpdateReq) -> EmployeeResp:
        """修改员工。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = OrgService(db)
            result = await svc.update_employee(emp_id, tenant_id, data.model_dump(exclude_unset=True))
            if not result:
                raise HTTPException(status_code=404, detail="employee not found")
            return EmployeeResp(**result)

    @router.delete("/employees/{emp_id}", response_model=dict)
    async def delete_employee(emp_id: int) -> dict:
        """删除员工。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = OrgService(db)
            deleted = await svc.delete_employee(emp_id, tenant_id)
            if not deleted:
                raise HTTPException(status_code=404, detail="employee not found")
            return {"deleted": True}

    # ── Skill 池 ────────────────────────────────────────────────────────

    @router.get("/skills", response_model=list)
    async def list_skills() -> list:
        """列出 skill 池。"""
        async with session_scope() as db, bypass_tenant_filter():
            svc = AgentSkillService(db)
            return await svc.list_pool()

    # ── 数字员工模板 ────────────────────────────────────────────────────

    @router.get("/templates", response_model=list)
    async def list_templates(
        department_id: Optional[int] = Query(None, description="按部门筛选"),
        template_type: Optional[str] = Query(None, description="按类型筛选"),
    ) -> list:
        """模板列表。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = TemplateService(db)
            return await svc.list_templates(tenant_id, department_id, template_type)

    @router.post("/templates", response_model=TemplateResp, status_code=201)
    async def create_template(data: TemplateCreateReq) -> TemplateResp:
        """创建模板。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = TemplateService(db)
            # TODO: 从认证上下文获取当前用户 ID
            result = await svc.create_template(tenant_id, created_by=1, data=data.model_dump())
            return TemplateResp(**result)

    @router.post("/templates/{template_id}/validate", response_model=dict)
    async def validate_template(template_id: int) -> dict:
        """触发 5 道自动检查。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = TemplateService(db)
            result = await svc.validate_template(template_id, tenant_id)
            if result is None:
                raise HTTPException(status_code=404, detail="template not found")
            return result

    @router.post("/templates/{template_id}/submit", response_model=dict)
    async def submit_template(template_id: int) -> dict:
        """提交审批。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = TemplateService(db)
            result = await svc.submit_template(template_id, tenant_id)
            if result is None:
                raise HTTPException(status_code=404, detail="template not found")
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            return result

    @router.post("/templates/{template_id}/approve", response_model=dict)
    async def approve_template(template_id: int) -> dict:
        """审批通过（创建 DigitalAgent）。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = TemplateService(db)
            # TODO: 从认证上下文获取审批人 ID
            result = await svc.approve_template(template_id, tenant_id, approved_by=1)
            if result is None:
                raise HTTPException(status_code=404, detail="template not found")
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            return result

    @router.post("/templates/{template_id}/reject", response_model=dict)
    async def reject_template(template_id: int) -> dict:
        """审批拒绝。"""
        tenant_id = get_tenant_context()
        if tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id not set")
        async with session_scope() as db, bypass_tenant_filter():
            svc = TemplateService(db)
            result = await svc.reject_template(template_id, tenant_id)
            if result is None:
                raise HTTPException(status_code=404, detail="template not found")
            if "error" in result:
                raise HTTPException(status_code=400, detail=result["error"])
            return result

    @router.get("/templates/download-sample", response_model=dict)
    async def download_template_sample() -> dict:
        """下载模板样板 JSON。"""
        return {
            "template_name": "示例模板",
            "template_type": "employee_created",
            "department_id": 1,
            "agent_name": "客服助手",
            "job_objective": "处理客户咨询和投诉",
            "role": "客服专员",
            "decision_scope": ["read", "create"],
            "work_boundary": "仅处理售前咨询，不涉及售后退款",
            "skills": [
                {
                    "skill_key": "ddw.llm.chat",
                    "proficiency": "expert",
                    "trigger_conditions": [{"event": "message_received"}],
                    "sla_seconds": 60,
                }
            ],
            "input_spec": {"type": "object", "properties": {"message": {"type": "string"}}},
            "output_spec": {"type": "object", "properties": {"reply": {"type": "string"}}},
        }

    return router


__all__ = ["build_router"]
