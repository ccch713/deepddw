"""DDW Commission - FastAPI router."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

from .calculator import calculate_for_period
from .models import (
    CommissionList,
    CommissionRecord,
    CommissionRule,
    CommissionRuleCreate,
    HealthResponse,
    RecordList,
)
from .store import CommissionStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw_commission", tags=["ddw_commission"]
)
_store: CommissionStore | None = None


def set_store(s: CommissionStore) -> None:
    global _store
    _store = s


def _ensure() -> None:
    if _store is None:
        raise HTTPException(status_code=503, detail="plugin not initialized")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    if _store is None:
        return HealthResponse()
    return HealthResponse(total_rules=_store.total_rules())


@router.post("/rules", response_model=CommissionRule, status_code=201)
async def create_rule(req: CommissionRuleCreate) -> CommissionRule:
    _ensure()
    if not (0 <= req.percentage <= 1):
        raise HTTPException(status_code=400, detail="percentage 必须在 0-1 之间")
    d = _store.create_rule(req.model_dump())
    return CommissionRule(**d)


@router.get("/rules", response_model=CommissionList)
async def list_rules(treatment_type: Optional[str] = None) -> CommissionList:
    _ensure()
    items = _store.list_rules(treatment_type)
    return CommissionList(total=len(items), rules=items)


@router.patch("/rules/{rule_id}", response_model=CommissionRule)
async def update_rule(rule_id: str, percentage: float, is_active: Optional[bool] = None) -> CommissionRule:
    _ensure()
    updates: dict = {}
    if percentage is not None:
        if not (0 <= percentage <= 1):
            raise HTTPException(status_code=400, detail="percentage 必须在 0-1 之间")
        updates["percentage"] = percentage
    if is_active is not None:
        updates["is_active"] = is_active
    r = _store.update_rule(rule_id, updates)
    if r is None:
        raise HTTPException(status_code=404, detail=f"rule not found: {rule_id}")
    return CommissionRule(**r)


@router.post("/calculate", response_model=RecordList)
async def calculate(period: str) -> RecordList:
    _ensure()
    if not period or len(period) != 7 or period[4] != "-":
        raise HTTPException(status_code=400, detail="period 格式 YYYY-MM")
    rules = _store.list_rules()
    previews = calculate_for_period(_store.db_path, period, rules)
    out: list[dict] = []
    for pv in previews:
        if pv["commission_amount"] <= 0:
            continue
        # 已存在的跳过
        existing = _store.list_records(period=period)
        if any(r["doctor_id"] == pv["doctor_id"] for r in existing):
            continue
        rule_applied = pv["breakdown"][0]["rule_id"] if pv["breakdown"] else "none"
        rec = _store.create_record({
            "doctor_id": pv["doctor_id"],
            "period": period,
            "total_income": pv["total_income"],
            "commission_amount": pv["commission_amount"],
            "rule_applied": rule_applied,
            "breakdown": pv["breakdown"],
        })
        out.append(rec)
    return RecordList(total=len(out), records=out)


@router.get("/records", response_model=RecordList)
async def list_records(period: Optional[str] = None) -> RecordList:
    _ensure()
    items = _store.list_records(period)
    return RecordList(total=len(items), records=items)


@router.post("/records/{record_id}/confirm", response_model=CommissionRecord)
async def confirm(record_id: str) -> CommissionRecord:
    _ensure()
    r = _store.get_record(record_id)
    if r is None:
        raise HTTPException(status_code=404, detail=f"record not found: {record_id}")
    if r["status"] == "confirmed":
        raise HTTPException(status_code=400, detail="已确认")
    updated = _store.update_record(
        record_id, {"status": "confirmed", "confirmed_at": datetime.now(timezone.utc).isoformat()}
    )
    return CommissionRecord(**updated)  # type: ignore[arg-type]
