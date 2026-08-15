"""DDW Aggregated Pay - FastAPI router."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from .models import (
    TX_STATUSES,
    ChannelList,
    HealthResponse,
    MismatchedItem,
    PayChannel,
    PayChannelCreate,
    PayTransaction,
    PayTransactionCreate,
    PayTransactionUpdate,
    ReconcileReport,
    TransactionList,
)
from .store import AggregatedPayStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw_aggregated_pay",
    tags=["ddw_aggregated_pay"],
)
_store: AggregatedPayStore | None = None


def set_store(s: AggregatedPayStore) -> None:
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
        total_channels=_store.total_channels(),
        total_transactions=_store.total_transactions(),
    )


@router.post("/channels", response_model=PayChannel, status_code=201)
async def create_channel(req: PayChannelCreate) -> PayChannel:
    _ensure()
    if not req.channel_name.strip():
        raise HTTPException(status_code=400, detail="channel_name 必填")
    d = _store.create_channel(req.model_dump())
    return PayChannel(**d)


@router.get("/channels", response_model=ChannelList)
async def list_channels() -> ChannelList:
    _ensure()
    items = _store.list_channels()
    return ChannelList(total=len(items), channels=items)


@router.post("/transactions", response_model=PayTransaction, status_code=201)
async def create_transaction(req: PayTransactionCreate) -> PayTransaction:
    _ensure()
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount 必须 > 0")
    d = _store.create_transaction(req.model_dump())
    return PayTransaction(**d)


@router.get("/transactions", response_model=TransactionList)
async def list_transactions(
    channel: Optional[str] = None, status: Optional[str] = None
) -> TransactionList:
    _ensure()
    if status and status not in TX_STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid status: {status}")
    items = _store.list_transactions(channel=channel, status=status)
    return TransactionList(total=len(items), transactions=items)


@router.get("/transactions/{transaction_id}", response_model=PayTransaction)
async def get_transaction(transaction_id: str) -> PayTransaction:
    _ensure()
    d = _store.get_transaction(transaction_id)
    if d is None:
        raise HTTPException(
            status_code=404, detail=f"transaction not found: {transaction_id}")
    return PayTransaction(**d)


@router.patch("/transactions/{transaction_id}", response_model=PayTransaction)
async def update_transaction(
    transaction_id: str, req: PayTransactionUpdate
) -> PayTransaction:
    _ensure()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if "status" in updates and updates["status"] not in TX_STATUSES:
        raise HTTPException(
            status_code=400, detail=f"invalid status: {updates['status']}")
    d = _store.update_transaction(transaction_id, updates)
    if d is None:
        raise HTTPException(
            status_code=404, detail=f"transaction not found: {transaction_id}")
    return PayTransaction(**d)


@router.post("/reconcile", response_model=ReconcileReport)
async def reconcile(date: str) -> ReconcileReport:
    _ensure()
    s = _store.reconcile(date)
    return ReconcileReport(
        date=s["date"],
        matched=s["matched"],
        mismatched=[MismatchedItem(**m) for m in s["mismatched"]],
        payment_total=s["payment_total"],
        transaction_total=s["transaction_total"],
        diff=s["diff"],
    )


@router.get("/reconcile-report", response_model=ReconcileReport)
async def reconcile_report(date: str) -> ReconcileReport:
    _ensure()
    s = _store.reconcile(date)
    return ReconcileReport(
        date=s["date"],
        matched=s["matched"],
        mismatched=[MismatchedItem(**m) for m in s["mismatched"]],
        payment_total=s["payment_total"],
        transaction_total=s["transaction_total"],
        diff=s["diff"],
    )
