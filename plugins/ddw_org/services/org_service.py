"""部门 / 数字员工 / 员工 CRUD 服务。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from plugins.ddw_org.models import (
    AgentSkill,
    Department,
    DigitalAgent,
    OrgEmployee,
    OrgSkillPool,
)

logger = logging.getLogger(__name__)

# 数字员工岗位卡可读写的 skill 字段
AGENT_SKILL_UPDATE_FIELDS = ("enabled", "proficiency", "trigger_conditions", "sla_seconds")


class OrgService:
    """组织 CRUD 服务。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── 部门 ────────────────────────────────────────────────────────────

    async def list_departments(self, tenant_id: int) -> List[Dict[str, Any]]:
        """部门列表（含 digital_agent_count + employee_count）。"""
        stmt = (
            select(
                Department,
                func.count(DigitalAgent.id).label("agent_count"),
                func.count(OrgEmployee.id).label("employee_count"),
            )
            .outerjoin(DigitalAgent, DigitalAgent.department_id == Department.id)
            .outerjoin(OrgEmployee, OrgEmployee.department_id == Department.id)
            .where(Department.tenant_id == tenant_id)
            .group_by(Department.id)
            .order_by(Department.sort_order)
        )
        rows = (await self.db.execute(stmt)).all()
        result = []
        for dept, agent_count, employee_count in rows:
            result.append({
                **_dept_to_dict(dept),
                "digital_agent_count": agent_count,
                "employee_count": employee_count,
            })
        return result

    async def get_department(self, dept_id: int, tenant_id: int) -> Optional[Dict[str, Any]]:
        """部门详情（含数字员工 + 员工列表）。"""
        dept = await self.db.get(Department, dept_id)
        if not dept or dept.tenant_id != tenant_id:
            return None
        agents = (
            await self.db.execute(
                select(DigitalAgent)
                .where(DigitalAgent.department_id == dept_id)
                .order_by(DigitalAgent.id)
            )
        ).scalars().all()
        employees = (
            await self.db.execute(
                select(OrgEmployee)
                .where(OrgEmployee.department_id == dept_id)
                .order_by(OrgEmployee.id)
            )
        ).scalars().all()
        return {
            **_dept_to_dict(dept),
            "agents": [_agent_to_dict(a) for a in agents],
            "employees": [_emp_to_dict(e) for e in employees],
        }

    async def update_department(
        self, dept_id: int, tenant_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """修改部门（含 manager_user_id）。"""
        dept = await self.db.get(Department, dept_id)
        if not dept or dept.tenant_id != tenant_id:
            return None
        if "name" in data:
            dept.name = data["name"]
        if "description" in data:
            dept.description = data["description"]
        if "sort_order" in data:
            dept.sort_order = data["sort_order"]
        if "manager_user_id" in data:
            dept.manager_user_id = data["manager_user_id"]
        await self.db.commit()
        await self.db.refresh(dept)
        return _dept_to_dict(dept)

    async def get_department_manager(
        self, dept_id: int, tenant_id: int
    ) -> Optional[Dict[str, Any]]:
        """获取部门负责人信息。"""
        dept = await self.db.get(Department, dept_id)
        if not dept or dept.tenant_id != tenant_id:
            return None
        if dept.manager_user_id is None:
            return None
        # 查询用户信息
        from sqlalchemy import text
        result = await self.db.execute(
            text("SELECT id, username, email FROM users WHERE id = :uid"),
            {"uid": dept.manager_user_id},
        )
        row = result.first()
        if not row:
            return None
        return {"id": row[0], "username": row[1], "email": row[2]}

    async def create_department(
        self, tenant_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """新建部门。"""
        dept = Department(
            tenant_id=tenant_id,
            name=data["name"],
            description=data.get("description", ""),
            sort_order=data.get("sort_order", 0),
            preset_id=data.get("preset_id"),
        )
        self.db.add(dept)
        await self.db.commit()
        await self.db.refresh(dept)
        return _dept_to_dict(dept)

    # ── 数字员工 ────────────────────────────────────────────────────────

    async def list_agents(
        self, tenant_id: int, department_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """数字员工列表。"""
        stmt = select(DigitalAgent).where(DigitalAgent.tenant_id == tenant_id)
        if department_id is not None:
            stmt = stmt.where(DigitalAgent.department_id == department_id)
        stmt = stmt.order_by(DigitalAgent.id)
        agents = (await self.db.execute(stmt)).scalars().all()
        return [_agent_to_dict(a) for a in agents]

    async def get_agent(self, agent_id: int, tenant_id: int) -> Optional[Dict[str, Any]]:
        """数字员工详情（含已分配 skill）。"""
        agent = await self.db.get(DigitalAgent, agent_id)
        if not agent or agent.tenant_id != tenant_id:
            return None
        # 查询已分配 skill
        skills_stmt = (
            select(AgentSkill, OrgSkillPool)
            .join(OrgSkillPool, OrgSkillPool.id == AgentSkill.skill_id)
            .where(AgentSkill.agent_id == agent_id)
            .order_by(AgentSkill.id)
        )
        skill_rows = (await self.db.execute(skills_stmt)).all()
        skills = []
        for askill, pool in skill_rows:
            skills.append({
                "id": askill.id,
                "skill_id": askill.skill_id,
                "skill_key": pool.skill_key,
                "name": pool.name,
                "enabled": askill.enabled,
                "assigned_at": askill.assigned_at,
            })
        return {**_agent_to_dict(agent), "skills": skills}

    async def update_agent(
        self, agent_id: int, tenant_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """修改数字员工（含新字段）。"""
        agent = await self.db.get(DigitalAgent, agent_id)
        if not agent or agent.tenant_id != tenant_id:
            return None
        for field in (
            "name", "role", "description", "avatar_color", "status",
            "job_objective", "report_to", "decision_scope", "work_boundary",
        ):
            if field in data:
                setattr(agent, field, data[field])
        await self.db.commit()
        await self.db.refresh(agent)
        return _agent_to_dict(agent)

    async def get_agent_job_card(
        self, agent_id: int, tenant_id: int
    ) -> Optional[Dict[str, Any]]:
        """获取数字员工完整岗位卡。"""
        agent = await self.db.get(DigitalAgent, agent_id)
        if not agent or agent.tenant_id != tenant_id:
            return None
        # 查询部门名
        dept = await self.db.get(Department, agent.department_id)
        dept_name = dept.name if dept else ""
        # 查询 report_to 用户名
        report_to_name = None
        if agent.report_to:
            from sqlalchemy import text
            result = await self.db.execute(
                text("SELECT username FROM users WHERE id = :uid"),
                {"uid": agent.report_to},
            )
            row = result.first()
            if row:
                report_to_name = row[0]
        # 查询已分配 skill
        skills_stmt = (
            select(AgentSkill, OrgSkillPool)
            .join(OrgSkillPool, OrgSkillPool.id == AgentSkill.skill_id)
            .where(AgentSkill.agent_id == agent_id)
            .order_by(AgentSkill.id)
        )
        skill_rows = (await self.db.execute(skills_stmt)).all()
        skills = []
        for askill, pool in skill_rows:
            skills.append({
                "skill_key": pool.skill_key,
                "name": pool.name,
                "proficiency": askill.proficiency,
                "trigger_conditions": askill.trigger_conditions or [],
                "sla_seconds": askill.sla_seconds,
            })
        return {
            "id": agent.id,
            "name": agent.name,
            "role": agent.role or "",
            "department_name": dept_name,
            "job_objective": agent.job_objective or "",
            "report_to_name": report_to_name,
            "decision_scope": agent.decision_scope or [],
            "work_boundary": agent.work_boundary or "",
            "skills": skills,
            "status": agent.status,
        }

    async def validate_agent(
        self, agent_id: int, tenant_id: int
    ) -> Optional[Dict[str, Any]]:
        """完整验证数字员工能力（P1 增强版）。

        验证项：
        C1: job_objective 非空
        C2: work_boundary 非空
        C3: 至少 1 个 skill
        C4: proficiency 枚举值合法（junior/senior/expert）
        C5: decision_scope 含 "approve" 时，至少有 1 个 expert 级 skill
        """
        agent = await self.db.get(DigitalAgent, agent_id)
        if not agent or agent.tenant_id != tenant_id:
            return None

        checks = []

        # C1: 岗位目标
        c1 = bool(agent.job_objective and agent.job_objective.strip())
        checks.append({"check": "C1", "name": "岗位目标", "passed": c1,
                        "message": "" if c1 else "job_objective 为空"})

        # C2: 工作边界
        c2 = bool(agent.work_boundary and agent.work_boundary.strip())
        checks.append({"check": "C2", "name": "工作边界", "passed": c2,
                        "message": "" if c2 else "work_boundary 为空"})

        # C3: 至少1个skill
        skills = (await self.db.execute(
            select(AgentSkill).where(AgentSkill.agent_id == agent_id)
        )).scalars().all()
        c3 = len(skills) > 0
        checks.append({"check": "C3", "name": "技能配置", "passed": c3,
                        "message": "" if c3 else "无任何技能配置"})

        # C4: proficiency 枚举校验
        valid_proficiencies = {"junior", "senior", "expert"}
        invalid_skills = [s for s in skills if s.proficiency not in valid_proficiencies]
        c4 = len(invalid_skills) == 0
        checks.append({"check": "C4", "name": "技能熟练度", "passed": c4,
                        "message": "" if c4 else f"无效熟练度: {[s.proficiency for s in invalid_skills]}"})

        # C5: approve 权限需 expert 级 skill
        has_approve = "approve" in (agent.decision_scope or [])
        has_expert = any(s.proficiency == "expert" for s in skills)
        c5 = not has_approve or has_expert
        checks.append({"check": "C5", "name": "审批权限与技能匹配", "passed": c5,
                        "message": "" if c5 else "decision_scope 含 approve 但无 expert 级技能"})

        all_passed = all(c["passed"] for c in checks)
        return {
            "agent_id": agent_id,
            "passed": all_passed,
            "checks": checks,
        }

    # ── 员工 ────────────────────────────────────────────────────────────

    async def list_employees(
        self, tenant_id: int, department_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """员工列表。"""
        stmt = select(OrgEmployee).where(OrgEmployee.tenant_id == tenant_id)
        if department_id is not None:
            stmt = stmt.where(OrgEmployee.department_id == department_id)
        stmt = stmt.order_by(OrgEmployee.id)
        employees = (await self.db.execute(stmt)).scalars().all()
        return [_emp_to_dict(e) for e in employees]

    async def create_employee(
        self, tenant_id: int, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """新增员工。"""
        emp = OrgEmployee(
            tenant_id=tenant_id,
            name=data["name"],
            phone=data.get("phone"),
            title=data.get("title", ""),
            department_id=data.get("department_id"),
            wecom_id=data.get("wecom_id"),
        )
        self.db.add(emp)
        await self.db.commit()
        await self.db.refresh(emp)
        return _emp_to_dict(emp)

    async def update_employee(
        self, emp_id: int, tenant_id: int, data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """修改员工。"""
        emp = await self.db.get(OrgEmployee, emp_id)
        if not emp or emp.tenant_id != tenant_id:
            return None
        for field in ("name", "phone", "title", "department_id", "wecom_id", "status"):
            if field in data:
                setattr(emp, field, data[field])
        await self.db.commit()
        await self.db.refresh(emp)
        return _emp_to_dict(emp)

    async def delete_employee(self, emp_id: int, tenant_id: int) -> bool:
        """删除员工。"""
        emp = await self.db.get(OrgEmployee, emp_id)
        if not emp or emp.tenant_id != tenant_id:
            return False
        await self.db.delete(emp)
        await self.db.commit()
        return True


# ── 序列化辅助 ──────────────────────────────────────────────────────────


def _dept_to_dict(d: Department) -> Dict[str, Any]:
    return {
        "id": d.id,
        "tenant_id": d.tenant_id,
        "name": d.name,
        "description": d.description or "",
        "sort_order": d.sort_order,
        "preset_id": d.preset_id,
        "manager_user_id": d.manager_user_id,
        "created_at": d.created_at,
        "updated_at": d.updated_at,
    }


def _agent_to_dict(a: DigitalAgent) -> Dict[str, Any]:
    return {
        "id": a.id,
        "tenant_id": a.tenant_id,
        "department_id": a.department_id,
        "name": a.name,
        "role": a.role or "",
        "avatar_color": a.avatar_color,
        "status": a.status,
        "description": a.description or "",
        "preset_id": a.preset_id,
        "default_skills": a.default_skills or [],
        "job_objective": a.job_objective or "",
        "report_to": a.report_to,
        "decision_scope": a.decision_scope or [],
        "work_boundary": a.work_boundary or "",
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


def _emp_to_dict(e: OrgEmployee) -> Dict[str, Any]:
    return {
        "id": e.id,
        "tenant_id": e.tenant_id,
        "department_id": e.department_id,
        "user_id": e.user_id,
        "name": e.name,
        "phone": e.phone,
        "title": e.title or "",
        "wecom_id": e.wecom_id,
        "source": e.source,
        "status": e.status,
        "created_at": e.created_at,
        "updated_at": e.updated_at,
    }


__all__ = ["OrgService"]
