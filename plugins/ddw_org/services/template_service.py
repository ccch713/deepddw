"""数字员工模板服务 — 5 道自动检查 + 审批流程。"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_org.models import (
    Department,
    DigitalAgent,
    DigitalAgentTemplate,
    OrgSkillPool,
)

logger = logging.getLogger(__name__)

VALID_DECISION_SCOPES = {
    "read", "create", "edit", "delete", "approve", "initiate_flow", "access_external",
}


class TemplateService:
    """数字员工模板 CRUD + 验证 + 审批服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── CRUD ─────────────────────────────────────────────────────────────

    async def list_templates(
        self,
        tenant_id: int,
        department_id: Optional[int] = None,
        template_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """模板列表。"""
        stmt = select(DigitalAgentTemplate).where(
            DigitalAgentTemplate.tenant_id == tenant_id
        )
        if department_id is not None:
            stmt = stmt.where(DigitalAgentTemplate.department_id == department_id)
        if template_type is not None:
            stmt = stmt.where(DigitalAgentTemplate.template_type == template_type)
        stmt = stmt.order_by(DigitalAgentTemplate.id.desc())
        rows = (await self.db.execute(stmt)).scalars().all()
        return [_template_to_dict(t) for t in rows]

    async def get_template(
        self, template_id: int, tenant_id: int
    ) -> Optional[Dict[str, Any]]:
        """模板详情。"""
        tpl = await self.db.get(DigitalAgentTemplate, template_id)
        if not tpl or tpl.tenant_id != tenant_id:
            return None
        return _template_to_dict(tpl)

    async def create_template(
        self, tenant_id: int, created_by: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """创建模板（status=draft）。"""
        tpl = DigitalAgentTemplate(
            tenant_id=tenant_id,
            template_name=data["template_name"],
            template_type=data.get("template_type", "employee_created"),
            created_by=created_by,
            department_id=data["department_id"],
            agent_name=data["agent_name"],
            job_objective=data.get("job_objective", ""),
            role=data["role"],
            decision_scope=data.get("decision_scope", []),
            work_boundary=data.get("work_boundary", ""),
            skills=data.get("skills", []),
            input_spec=data.get("input_spec"),
            output_spec=data.get("output_spec"),
            status="draft",
            approval_status="pending",
        )
        self.db.add(tpl)
        await self.db.commit()
        await self.db.refresh(tpl)
        return _template_to_dict(tpl)

    # ── 5 道自动检查 ────────────────────────────────────────────────────

    async def validate_template(
        self, template_id: int, tenant_id: int
    ) -> Optional[Dict[str, Any]]:
        """5 道自动检查。

        C1: 字段完整性
        C2: 部门归属
        C3: 技能有效性
        C4: 规范合理性（input/output spec 格式）
        C5: 权限边界（decision_scope 枚举值合法）
        """
        tpl = await self.db.get(DigitalAgentTemplate, template_id)
        if not tpl or tpl.tenant_id != tenant_id:
            return None

        results: List[Dict[str, Any]] = []

        # C1: 字段完整性
        c1_fields = ["agent_name", "job_objective", "role", "work_boundary", "skills"]
        missing = [f for f in c1_fields if not getattr(tpl, f, None)]
        results.append({
            "check": "C1",
            "name": "字段完整性",
            "passed": len(missing) == 0,
            "message": f"缺失字段: {missing}" if missing else "",
        })

        # C2: 部门归属
        dept = await self.db.get(Department, tpl.department_id)
        c2 = dept is not None and dept.tenant_id == tenant_id
        results.append({
            "check": "C2",
            "name": "部门归属",
            "passed": c2,
            "message": "" if c2 else "部门不存在或不属于当前租户",
        })

        # C3: 技能有效性
        registered_skills = (
            await self.db.execute(select(OrgSkillPool))
        ).scalars().all()
        registered_keys = {s.skill_key for s in registered_skills}
        template_keys = {s.get("skill_key") for s in (tpl.skills or [])}
        unregistered = template_keys - registered_keys
        c3 = len(unregistered) == 0
        results.append({
            "check": "C3",
            "name": "技能有效性",
            "passed": c3,
            "message": f"未注册技能: {unregistered}" if unregistered else "",
        })

        # C4: 规范合理性（input/output spec 格式）
        c4 = True
        if tpl.input_spec is not None and not isinstance(tpl.input_spec, dict):
            c4 = False
        if tpl.output_spec is not None and not isinstance(tpl.output_spec, dict):
            c4 = False
        results.append({
            "check": "C4",
            "name": "规范合理性",
            "passed": c4,
            "message": "" if c4 else "input_spec/output_spec 格式不正确",
        })

        # C5: 权限边界
        invalid = set(tpl.decision_scope or []) - VALID_DECISION_SCOPES
        c5 = len(invalid) == 0
        results.append({
            "check": "C5",
            "name": "权限边界",
            "passed": c5,
            "message": f"无效权限: {invalid}" if invalid else "",
        })

        all_passed = all(r["passed"] for r in results)
        tpl.validation_results = {"passed": all_passed, "results": results}
        tpl.status = "validation_passed" if all_passed else "draft"
        await self.db.commit()

        return {"passed": all_passed, "results": results}

    # ── 审批流程 ─────────────────────────────────────────────────────────

    async def submit_template(
        self, template_id: int, tenant_id: int
    ) -> Optional[Dict[str, Any]]:
        """提交审批（前提：validation_passed）。"""
        tpl = await self.db.get(DigitalAgentTemplate, template_id)
        if not tpl or tpl.tenant_id != tenant_id:
            return None
        if tpl.status != "validation_passed":
            return {"error": f"当前状态 {tpl.status} 不允许提交审批，需先通过验证"}
        tpl.status = "pending_department_approval"
        tpl.approval_status = "pending"
        await self.db.commit()
        await self.db.refresh(tpl)
        return _template_to_dict(tpl)

    async def approve_template(
        self, template_id: int, tenant_id: int, approved_by: int
    ) -> Optional[Dict[str, Any]]:
        """审批通过，创建 DigitalAgent。"""
        tpl = await self.db.get(DigitalAgentTemplate, template_id)
        if not tpl or tpl.tenant_id != tenant_id:
            return None
        if tpl.status != "pending_department_approval":
            return {"error": f"当前状态 {tpl.status} 不允许审批"}

        # 创建 DigitalAgent
        agent = DigitalAgent(
            tenant_id=tenant_id,
            department_id=tpl.department_id,
            name=tpl.agent_name,
            role=tpl.role,
            job_objective=tpl.job_objective,
            decision_scope=tpl.decision_scope,
            work_boundary=tpl.work_boundary,
            default_skills=[s.get("skill_key") for s in (tpl.skills or [])],
        )
        self.db.add(agent)

        # 更新模板状态
        tpl.status = "active"
        tpl.approval_status = "approved"
        tpl.approved_by = approved_by
        tpl.approved_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(agent)

        return {"agent_id": agent.id, "template_id": template_id, "status": "created"}

    async def reject_template(
        self, template_id: int, tenant_id: int
    ) -> Optional[Dict[str, Any]]:
        """审批拒绝，退回 draft。"""
        tpl = await self.db.get(DigitalAgentTemplate, template_id)
        if not tpl or tpl.tenant_id != tenant_id:
            return None
        if tpl.status != "pending_department_approval":
            return {"error": f"当前状态 {tpl.status} 不允许拒绝"}
        tpl.status = "draft"
        tpl.approval_status = "rejected"
        await self.db.commit()
        await self.db.refresh(tpl)
        return _template_to_dict(tpl)


def _template_to_dict(tpl: DigitalAgentTemplate) -> Dict[str, Any]:
    return {
        "id": tpl.id,
        "tenant_id": tpl.tenant_id,
        "template_name": tpl.template_name,
        "template_type": tpl.template_type,
        "created_by": tpl.created_by,
        "department_id": tpl.department_id,
        "agent_name": tpl.agent_name,
        "job_objective": tpl.job_objective or "",
        "role": tpl.role,
        "decision_scope": tpl.decision_scope or [],
        "work_boundary": tpl.work_boundary or "",
        "skills": tpl.skills or [],
        "input_spec": tpl.input_spec,
        "output_spec": tpl.output_spec,
        "status": tpl.status,
        "validation_results": tpl.validation_results,
        "approval_status": tpl.approval_status,
        "approved_by": tpl.approved_by,
        "approved_at": tpl.approved_at,
        "created_at": tpl.created_at,
        "updated_at": tpl.updated_at,
    }


__all__ = ["TemplateService"]
