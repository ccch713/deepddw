"""员工花名册 API 路由"""
from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from core.database.session import session_scope
from core.database.tenant_filter import bypass_tenant_filter
from plugins.ddw_employee_roster.models import Employee, EmployeeTrainingRecord


class EmployeeReq(BaseModel):
    employee_no: str
    name: str
    department: str = ""
    position: str = ""
    phone: str = ""
    email: str = ""

async def list_employees() -> List[Dict[str, Any]]:
    async with session_scope() as s, bypass_tenant_filter():
        rows = (await s.execute(select(Employee))).scalars().all()
    return [{"id": e.id, "employee_no": e.employee_no, "name": e.name, "department": e.department, "position": e.position} for e in rows]

async def get_employee(employee_id: int) -> Dict[str, Any]:
    async with session_scope() as s, bypass_tenant_filter():
        e = (await s.execute(select(Employee).where(Employee.id == employee_id))).scalar_one_or_none()
    if not e:
        return {"error": "not found"}
    return {"id": e.id, "employee_no": e.employee_no, "name": e.name, "department": e.department, "position": e.position, "status": e.status}

async def create_employee(req: EmployeeReq) -> Dict[str, Any]:
    async with session_scope() as s, bypass_tenant_filter():
        emp = Employee(employee_no=req.employee_no, name=req.name, department=req.department, position=req.position, phone=req.phone, email=req.email)
        s.add(emp)
        await s.commit()
        await s.refresh(emp)
    return {"id": emp.id, "employee_no": emp.employee_no, "name": emp.name}

async def employee_training(employee_id: int) -> List[Dict[str, Any]]:
    async with session_scope() as s, bypass_tenant_filter():
        rows = (await s.execute(select(EmployeeTrainingRecord).where(EmployeeTrainingRecord.employee_id == employee_id))).scalars().all()
    return [{"id": r.id, "subject": r.subject, "score": r.score, "grade": r.grade, "duration_minutes": r.duration_minutes} for r in rows]

async def departments() -> List[str]:
    async with session_scope() as s, bypass_tenant_filter():
        rows = (await s.execute(select(Employee.department).distinct())).scalars().all()
    return [d for d in rows if d]

def build_router(plugin) -> APIRouter:
    r = APIRouter(prefix=plugin.router_prefix, tags=[plugin.name])
    r.add_api_route("/employees", list_employees, methods=["GET"])
    r.add_api_route("/employees", create_employee, methods=["POST"])
    r.add_api_route("/employees/{employee_id}", get_employee, methods=["GET"])
    r.add_api_route("/employees/{employee_id}/training", employee_training, methods=["GET"])
    r.add_api_route("/departments", departments, methods=["GET"])
    return r
