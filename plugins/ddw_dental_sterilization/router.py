"""DDW Dental Sterilization - FastAPI router."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from .models import (
    CYCLE_TYPES,
    INDICATOR_RESULTS,
    BatchCreate,
    BatchList,
    ComplianceResponse,
    HealthResponse,
    SterilizationBatch,
    Sterilizer,
    SterilizerCreate,
    TraceResponse,
)
from .store import SterilizationStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw_dental_sterilization",
    tags=["ddw_dental_sterilization"],
)
_store: SterilizationStore | None = None


def set_store(s: SterilizationStore) -> None:
    global _store
    _store = s


def _ensure() -> None:
    if _store is None:
        raise HTTPException(status_code=503, detail="plugin not initialized")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    if _store is None:
        return HealthResponse()
    return HealthResponse(
        total_batches=_store.total_batches(),
        total_sterilizers=_store.total_sterilizers(),
    )


@router.post("/sterilizers", response_model=Sterilizer, status_code=201)
async def create_sterilizer(req: SterilizerCreate) -> Sterilizer:
    _ensure()
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name 必填")
    d = _store.create_sterilizer(req.model_dump())
    return Sterilizer(**d)


@router.get("/sterilizers", response_model=list[Sterilizer])
async def list_sterilizers() -> list[Sterilizer]:
    _ensure()
    return [Sterilizer(**d) for d in _store.list_sterilizers()]


@router.post("/batches", response_model=SterilizationBatch, status_code=201)
async def create_batch(req: BatchCreate) -> SterilizationBatch:
    _ensure()
    if req.cycle_type not in CYCLE_TYPES:
        raise HTTPException(status_code=400, detail=f"invalid cycle_type: {req.cycle_type}")
    if req.indicator_result not in INDICATOR_RESULTS:
        raise HTTPException(status_code=400, detail=f"invalid indicator_result: {req.indicator_result}")
    if not req.batch_number.strip():
        raise HTTPException(status_code=400, detail="batch_number 必填")
    try:
        d = _store.create_batch(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return SterilizationBatch(**d)


@router.get("/batches", response_model=BatchList)
async def list_batches(sterilizer_id: Optional[str] = None) -> BatchList:
    _ensure()
    items = _store.list_batches(sterilizer_id=sterilizer_id)
    return BatchList(total=len(items), batches=items)


@router.get("/batches/{batch_id}/trace", response_model=TraceResponse)
async def trace_batch(batch_id: str) -> TraceResponse:
    _ensure()
    b = _store.get_batch(batch_id)
    if b is None:
        raise HTTPException(status_code=404, detail=f"batch not found: {batch_id}")
    # 简单追溯: 关联的 used_by_record_id + 找 ddw_dental_emr 的患者
    patients: list[str] = []
    record_ids: list[str] = []
    if b.get("used_by_record_id"):
        record_ids.append(b["used_by_record_id"])
        # 跨插件读 EMR db
        emr_db = _store.db_path.parent.parent / "ddw_dental_emr" / "data" / "dental_emr.db"
        emr_db2 = _store.db_path.parent / "dental_emr.db"
        target = emr_db if emr_db.exists() else (emr_db2 if emr_db2.exists() else None)
        if target:
            import sqlite3
            try:
                with sqlite3.connect(target, timeout=5) as conn:
                    conn.row_factory = sqlite3.Row
                    row = conn.execute(
                        "SELECT patient_id FROM dental_records WHERE id=?",
                        (b["used_by_record_id"],),
                    ).fetchone()
                    if row:
                        patients.append(row["patient_id"])
            except sqlite3.Error:
                pass
    return TraceResponse(batch_id=batch_id, patients=patients, record_ids=record_ids)


@router.get("/expiring", response_model=BatchList)
async def expiring() -> BatchList:
    _ensure()
    items = _store.expiring_soon()
    return BatchList(total=len(items), batches=items)


@router.get("/compliance", response_model=ComplianceResponse)
async def compliance(period: str) -> ComplianceResponse:
    _ensure()
    s = _store.compliance(period)
    return ComplianceResponse(**s)
