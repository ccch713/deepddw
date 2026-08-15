"""DDW Patient CRM - FastAPI router."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from .models import (
    SOURCE_VALUES,
    HealthResponse,
    Patient,
    PatientCreate,
    PatientList,
    PatientUpdate,
    StatsResponse,
    VisitsResponse,
    VisitSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw_patient_crm", tags=["ddw_patient_crm"]
)

# 由 plugin.py 注入
_store: Any = None


def set_store(store: Any) -> None:
    global _store
    _store = store


def _ensure() -> None:
    if _store is None:
        raise HTTPException(status_code=503, detail="plugin not initialized")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    total = _store.total_count() if _store else 0
    return HealthResponse(total_patients=total)


@router.post("/patients", response_model=Patient, status_code=201)
async def create_patient(req: PatientCreate) -> Patient:
    _ensure()
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name 必填且非空")
    if not req.phone.strip():
        raise HTTPException(status_code=400, detail="phone 必填")
    if req.source not in SOURCE_VALUES:
        raise HTTPException(status_code=400, detail=f"invalid source: {req.source}")
    try:
        data = _store.create(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return Patient(**data)


@router.get("/patients/{patient_id}", response_model=Patient)
async def get_patient(patient_id: str) -> Patient:
    _ensure()
    data = _store.get(patient_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"patient not found: {patient_id}")
    return Patient(**data)


@router.get("/patients", response_model=PatientList)
async def list_patients(
    name: Optional[str] = None,
    phone: Optional[str] = None,
    tag: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> PatientList:
    _ensure()
    page = max(page, 1)
    if page_size < 1 or page_size > 200:
        page_size = 20
    data = _store.search(name=name, phone=phone, tag=tag, page=page, page_size=page_size)
    return PatientList(total=data["total"], patients=data["patients"])


@router.patch("/patients/{patient_id}", response_model=Patient)
async def update_patient(patient_id: str, req: PatientUpdate) -> Patient:
    _ensure()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if "source" in updates and updates["source"] not in SOURCE_VALUES:
        raise HTTPException(status_code=400, detail=f"invalid source: {updates['source']}")
    try:
        data = _store.update(patient_id, updates)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if data is None:
        raise HTTPException(status_code=404, detail=f"patient not found: {patient_id}")
    return Patient(**data)


@router.get("/patients/{patient_id}/visits", response_model=VisitsResponse)
async def list_visits(patient_id: str) -> VisitsResponse:
    _ensure()
    if _store.get(patient_id) is None:
        raise HTTPException(status_code=404, detail=f"patient not found: {patient_id}")
    rows = _store.list_visits(patient_id)
    return VisitsResponse(
        patient_id=patient_id,
        total=len(rows),
        visits=[VisitSummary(**r) for r in rows],
    )


@router.get("/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    _ensure()
    s = _store.stats()
    return StatsResponse(**s)
