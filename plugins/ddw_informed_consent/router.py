"""DDW Informed Consent - FastAPI router."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

from .models import (
    CONSENT_TYPES,
    ConsentCreate,
    ConsentList,
    ConsentRecord,
    ConsentSign,
    HealthResponse,
    TemplateInfo,
    TemplateList,
)
from .store import ConsentStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw_informed_consent",
    tags=["ddw_informed_consent"],
)
_store: ConsentStore | None = None


def set_store(s: ConsentStore) -> None:
    global _store
    _store = s


def _ensure() -> None:
    if _store is None:
        raise HTTPException(status_code=503, detail="plugin not initialized")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    if _store is None:
        return HealthResponse()
    return HealthResponse(total_consents=_store.total_count())


@router.post("/records", response_model=ConsentRecord, status_code=201)
async def create_record(req: ConsentCreate) -> ConsentRecord:
    _ensure()
    if req.consent_type not in CONSENT_TYPES:
        raise HTTPException(status_code=400, detail=f"invalid consent_type: {req.consent_type}")
    if not req.patient_id:
        raise HTTPException(status_code=400, detail="patient_id 必填")
    if not req.template_content.strip():
        raise HTTPException(status_code=400, detail="template_content 必填")
    d = _store.create(req.model_dump())
    return ConsentRecord(**d)


@router.get("/records", response_model=ConsentList)
async def list_records(patient_id: Optional[str] = None) -> ConsentList:
    _ensure()
    items = _store.list_for_patient(patient_id) if patient_id else _store.list_all()
    return ConsentList(total=len(items), records=items)


@router.get("/records/{record_id}", response_model=ConsentRecord)
async def get_record(record_id: str) -> ConsentRecord:
    _ensure()
    d = _store.get(record_id)
    if d is None:
        raise HTTPException(status_code=404, detail=f"consent not found: {record_id}")
    return ConsentRecord(**d)


@router.post("/records/{record_id}/sign", response_model=ConsentRecord)
async def sign(record_id: str, req: ConsentSign) -> ConsentRecord:
    _ensure()
    d = _store.get(record_id)
    if d is None:
        raise HTTPException(status_code=404, detail=f"consent not found: {record_id}")
    if d["status"] == "signed":
        raise HTTPException(status_code=400, detail="已签名")
    now = datetime.now(timezone.utc).isoformat()
    updates = {
        "status": "signed",
        "patient_signature": req.patient_signature,
        "signed_at": now,
    }
    if req.witness:
        updates["witness"] = req.witness
    updated = _store.update(record_id, updates)
    return ConsentRecord(**updated)  # type: ignore[arg-type]


@router.post("/records/{record_id}/revoke", response_model=ConsentRecord)
async def revoke(record_id: str) -> ConsentRecord:
    _ensure()
    d = _store.get(record_id)
    if d is None:
        raise HTTPException(status_code=404, detail=f"consent not found: {record_id}")
    if d["status"] == "revoked":
        raise HTTPException(status_code=400, detail="已撤销")
    updated = _store.update(record_id, {"status": "revoked"})
    return ConsentRecord(**updated)  # type: ignore[arg-type]


@router.get("/templates", response_model=TemplateList)
async def list_templates() -> TemplateList:
    _ensure()
    items = [TemplateInfo(**t) for t in _store.list_templates()]
    return TemplateList(total=len(items), templates=items)
