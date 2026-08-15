"""FastAPI router for CAPA Workflow plugin."""
from __future__ import annotations

import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/plugins/ddw-capa-workflow", tags=["capa-workflow"])
_service = None


def set_service(service):
    global _service
    _service = service


class CAPACreateRequest(BaseModel):
    title: str
    description: str
    source: str
    severity: str = "major"
    category: str = "general"
    assigned_to: str = ""
    due_date: Optional[str] = None  # ISO format
    created_by: str = "system"


class TransitionRequest(BaseModel):
    to_status: str
    comment: str = ""
    changed_by: str = "system"


class InvestigationRequest(BaseModel):
    root_cause: str
    method: str = "5why"
    changed_by: str = "system"


class ActionsRequest(BaseModel):
    corrective: str = ""
    preventive: str = ""
    changed_by: str = "system"


class EffectivenessRequest(BaseModel):
    check_result: str
    changed_by: str = "system"


@router.post("/capa")
async def create_capa(req: CAPACreateRequest):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    due = datetime.datetime.fromisoformat(req.due_date) if req.due_date else None
    capa = _service.create_capa(
        title=req.title, description=req.description, source=req.source,
        severity=req.severity, category=req.category, assigned_to=req.assigned_to,
        due_date=due, created_by=req.created_by
    )
    return {"id": capa.id, "capa_number": capa.capa_number, "status": capa.status}


@router.get("/capa")
async def list_capas(status: Optional[str] = None, severity: Optional[str] = None,
                     source: Optional[str] = None, assigned_to: Optional[str] = None,
                     limit: int = 50):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    capas = _service.list_capas(status=status, severity=severity, source=source,
                                assigned_to=assigned_to, limit=limit)
    return [{"id": c.id, "capa_number": c.capa_number, "title": c.title,
             "status": c.status, "severity": c.severity, "source": c.source,
             "assigned_to": c.assigned_to, "created_at": c.created_at.isoformat()} for c in capas]


@router.get("/capa/{capa_id}")
async def get_capa(capa_id: int):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    capa = _service.get_capa(capa_id)
    if not capa:
        raise HTTPException(404, "CAPA not found")
    return {"id": capa.id, "capa_number": capa.capa_number, "title": capa.title,
            "description": capa.description, "source": capa.source,
            "severity": capa.severity, "status": capa.status,
            "root_cause": capa.root_cause, "root_cause_method": capa.root_cause_method,
            "corrective_action": capa.corrective_action,
            "preventive_action": capa.preventive_action,
            "effectiveness_check": capa.effectiveness_check,
            "assigned_to": capa.assigned_to, "due_date": str(capa.due_date) if capa.due_date else None}


@router.post("/capa/{capa_id}/transition")
async def transition(capa_id: int, req: TransitionRequest):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    try:
        capa = _service.transition(capa_id, req.to_status, req.comment, req.changed_by)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not capa:
        raise HTTPException(404, "CAPA not found")
    return {"id": capa.id, "status": capa.status}


@router.post("/capa/{capa_id}/investigation")
async def add_investigation(capa_id: int, req: InvestigationRequest):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    capa = _service.add_investigation(capa_id, req.root_cause, req.method, req.changed_by)
    if not capa:
        raise HTTPException(404, "CAPA not found")
    return {"id": capa.id, "root_cause": capa.root_cause}


@router.post("/capa/{capa_id}/actions")
async def add_actions(capa_id: int, req: ActionsRequest):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    capa = _service.add_actions(capa_id, req.corrective, req.preventive, req.changed_by)
    if not capa:
        raise HTTPException(404, "CAPA not found")
    return {"id": capa.id, "corrective_action": capa.corrective_action,
            "preventive_action": capa.preventive_action}


@router.post("/capa/{capa_id}/effectiveness")
async def add_effectiveness(capa_id: int, req: EffectivenessRequest):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    capa = _service.add_effectiveness_check(capa_id, req.check_result, req.changed_by)
    if not capa:
        raise HTTPException(404, "CAPA not found")
    return {"id": capa.id, "effectiveness_check": capa.effectiveness_check}


@router.get("/capa/{capa_id}/history")
async def get_history(capa_id: int):
    if not _service:
        raise HTTPException(503, "Service not initialized")
    return [{"id": h.id, "from_status": h.from_status, "to_status": h.to_status,
             "comment": h.comment, "changed_by": h.changed_by,
             "created_at": h.created_at.isoformat()} for h in _service.get_history(capa_id)]


@router.get("/statistics")
async def get_statistics():
    if not _service:
        raise HTTPException(503, "Service not initialized")
    return _service.get_statistics()


@router.get("/overdue")
async def get_overdue():
    if not _service:
        raise HTTPException(503, "Service not initialized")
    capas = _service.get_overdue_capas()
    return [{"id": c.id, "capa_number": c.capa_number, "title": c.title,
             "due_date": str(c.due_date), "status": c.status} for c in capas]


@router.get("/health")
async def health():
    return {"status": "ok", "plugin": "ddw-capa-workflow", "version": "1.0.0"}
