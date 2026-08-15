"""DDW Doctor Schedule - FastAPI router."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from .models import (
    SLOT_TYPES,
    Doctor,
    DoctorCreate,
    DoctorList,
    DoctorUpdate,
    HealthResponse,
    ScheduleSlot,
    ScheduleSlotCreate,
    ScheduleSlotUpdate,
    SlotList,
)
from .store import DoctorStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw_doctor_schedule",
    tags=["ddw_doctor_schedule"],
)
_store: DoctorStore | None = None


def set_store(s: DoctorStore) -> None:
    global _store
    _store = s


def _ensure() -> None:
    if _store is None:
        raise HTTPException(status_code=503, detail="plugin not initialized")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    if _store is None:
        return HealthResponse()
    return HealthResponse(total_doctors=_store.total_doctors(), total_slots=_store.total_slots())


@router.post("/doctors", response_model=Doctor, status_code=201)
async def create_doctor(req: DoctorCreate) -> Doctor:
    _ensure()
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name 必填")
    d = _store.create_doctor(req.model_dump())
    return Doctor(**d)


@router.get("/doctors", response_model=DoctorList)
async def list_doctors(active_only: bool = False) -> DoctorList:
    _ensure()
    items = _store.list_doctors(active_only=active_only)
    return DoctorList(total=len(items), doctors=items)


@router.get("/doctors/{doctor_id}", response_model=Doctor)
async def get_doctor(doctor_id: str) -> Doctor:
    _ensure()
    d = _store.get_doctor(doctor_id)
    if d is None:
        raise HTTPException(status_code=404, detail=f"doctor not found: {doctor_id}")
    return Doctor(**d)


@router.patch("/doctors/{doctor_id}", response_model=Doctor)
async def update_doctor(doctor_id: str, req: DoctorUpdate) -> Doctor:
    _ensure()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    d = _store.update_doctor(doctor_id, updates)
    if d is None:
        raise HTTPException(status_code=404, detail=f"doctor not found: {doctor_id}")
    return Doctor(**d)


@router.post("/slots", response_model=ScheduleSlot, status_code=201)
async def create_slot(req: ScheduleSlotCreate) -> ScheduleSlot:
    _ensure()
    if req.slot_type not in SLOT_TYPES:
        raise HTTPException(status_code=400, detail=f"invalid slot_type: {req.slot_type}")
    if _store.get_doctor(req.doctor_id) is None:
        raise HTTPException(status_code=400, detail=f"doctor 不存在: {req.doctor_id}")
    try:
        s = _store.create_slot(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return ScheduleSlot(**s)


@router.get("/slots", response_model=SlotList)
async def list_slots(
    date: Optional[str] = None,
    doctor_id: Optional[str] = None,
    week: Optional[str] = None,
) -> SlotList:
    _ensure()
    rows = _store.list_slots(date=date, doctor_id=doctor_id, week=week)
    return SlotList(total=len(rows), slots=rows)


@router.patch("/slots/{slot_id}", response_model=ScheduleSlot)
async def update_slot(slot_id: str, req: ScheduleSlotUpdate) -> ScheduleSlot:
    _ensure()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if "slot_type" in updates and updates["slot_type"] not in SLOT_TYPES:
        raise HTTPException(status_code=400, detail=f"invalid slot_type: {updates['slot_type']}")
    s = _store.update_slot(slot_id, updates)
    if s is None:
        raise HTTPException(status_code=404, detail=f"slot not found: {slot_id}")
    return ScheduleSlot(**s)


@router.get("/doctors/{doctor_id}/slots", response_model=SlotList)
async def doctor_slots(doctor_id: str, week: Optional[str] = None) -> SlotList:
    _ensure()
    if _store.get_doctor(doctor_id) is None:
        raise HTTPException(status_code=404, detail=f"doctor not found: {doctor_id}")
    rows = _store.list_slots(doctor_id=doctor_id, week=week)
    return SlotList(total=len(rows), slots=rows)
