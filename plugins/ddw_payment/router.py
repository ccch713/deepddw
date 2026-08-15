"""DDW Payment - FastAPI router."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException

from .models import (
    PAYMENT_METHODS,
    STATUSES,
    DailySummary,
    HealthResponse,
    PaymentCreate,
    PaymentList,
    PaymentRecord,
    PaymentUpdate,
    RefundRequest,
)
from .store import PaymentStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/plugins/ddw_payment", tags=["ddw_payment"])
_store: PaymentStore | None = None


def set_store(s: PaymentStore) -> None:
    global _store
    _store = s


def _ensure() -> None:
    if _store is None:
        raise HTTPException(status_code=503, detail="plugin not initialized")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    if _store is None:
        return HealthResponse()
    return HealthResponse(total_records=_store.total_count())


@router.post("/records", response_model=PaymentRecord, status_code=201)
async def create_record(req: PaymentCreate) -> PaymentRecord:
    _ensure()
    if not req.items:
        raise HTTPException(status_code=400, detail="items 不能为空")
    if req.payment_method not in PAYMENT_METHODS:
        raise HTTPException(
            status_code=400, detail=f"invalid payment_method: {req.payment_method}")
    # 校验 items + 计算 total
    items_data = [item.model_dump() for item in req.items]
    total = sum(it["subtotal"] for it in items_data)
    if abs(total - sum(it["unit_price"] * it["quantity"] for it in items_data)) > 0.01:
        raise HTTPException(
            status_code=400, detail="subtotal 必须 = unit_price × quantity")
    actual = total - req.discount_amount
    payload = req.model_dump()
    payload["total_amount"] = round(total, 2)
    payload["actual_amount"] = round(actual, 2)
    payload["items"] = items_data
    d = _store.create(payload)
    return PaymentRecord(**d)


@router.get("/records/{record_id}", response_model=PaymentRecord)
async def get_record(record_id: str) -> PaymentRecord:
    _ensure()
    r = _store.get(record_id)
    if r is None:
        raise HTTPException(status_code=404, detail=f"record not found: {record_id}")
    return PaymentRecord(**r)


@router.get("/records", response_model=PaymentList)
async def list_records(
    date: Optional[str] = None,
    patient_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> PaymentList:
    _ensure()
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid status: {status}")
    data = _store.list_records(
        date=date, patient_id=patient_id, doctor_id=doctor_id,
        status=status, page=page, page_size=page_size,
    )
    return PaymentList(total=data["total"], records=data["records"])


@router.post("/records/{record_id}/pay", response_model=PaymentRecord)
async def mark_paid(record_id: str) -> PaymentRecord:
    _ensure()
    r = _store.get(record_id)
    if r is None:
        raise HTTPException(status_code=404, detail=f"record not found: {record_id}")
    if r["status"] == "paid":
        raise HTTPException(status_code=400, detail="已支付，无需重复操作")
    if r["status"] == "refunded":
        raise HTTPException(status_code=400, detail="已退款的记录不能再支付")
    now = datetime.now(timezone.utc).isoformat()
    updated = _store.update(record_id, {"status": "paid", "paid_at": now})
    return PaymentRecord(**updated)  # type: ignore[arg-type]


@router.post("/records/{record_id}/refund", response_model=PaymentRecord)
async def refund(record_id: str, req: RefundRequest) -> PaymentRecord:
    _ensure()
    r = _store.get(record_id)
    if r is None:
        raise HTTPException(status_code=404, detail=f"record not found: {record_id}")
    if r["status"] != "paid":
        raise HTTPException(status_code=400, detail="只能退款已支付记录")
    refund_amount = req.refund_amount if req.refund_amount is not None else r["actual_amount"]
    if refund_amount > r["actual_amount"]:
        raise HTTPException(status_code=400, detail="退款金额不能超过实收金额")
    updates = {"status": "refunded", "notes": (
        r.get("notes") or "") + f" | refund={refund_amount} reason={req.reason or '-'}"}
    updated = _store.update(record_id, updates)
    return PaymentRecord(**updated)  # type: ignore[arg-type]


@router.patch("/records/{record_id}", response_model=PaymentRecord)
async def update_record(record_id: str, req: PaymentUpdate) -> PaymentRecord:
    _ensure()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if "status" in updates and updates["status"] not in STATUSES:
        raise HTTPException(
            status_code=400, detail=f"invalid status: {updates['status']}")
    if "payment_method" in updates and updates["payment_method"] not in PAYMENT_METHODS:
        raise HTTPException(
            status_code=400, detail=f"invalid payment_method: {updates['payment_method']}")
    r = _store.update(record_id, updates)
    if r is None:
        raise HTTPException(status_code=404, detail=f"record not found: {record_id}")
    return PaymentRecord(**r)


@router.get("/daily-summary", response_model=DailySummary)
async def daily_summary(date: str) -> DailySummary:
    _ensure()
    return DailySummary(**_store.daily_summary(date))
