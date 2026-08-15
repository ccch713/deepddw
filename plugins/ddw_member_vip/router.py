"""DDW Member VIP - FastAPI router."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from .models import (
    AccountList,
    ConsumeRequest,
    HealthResponse,
    LevelStat,
    MemberAccount,
    MemberAccountCreate,
    RechargeRequest,
    StatsResponse,
    TransactionList,
)
from .store import MemberStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw_member_vip", tags=["ddw_member_vip"]
)
_store: MemberStore | None = None


def set_store(s: MemberStore) -> None:
    global _store
    _store = s


def _ensure() -> None:
    if _store is None:
        raise HTTPException(status_code=503, detail="plugin not initialized")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    if _store is None:
        return HealthResponse()
    return HealthResponse(total_accounts=_store.total_accounts())


@router.post("/accounts", response_model=MemberAccount, status_code=201)
async def create_account(req: MemberAccountCreate) -> MemberAccount:
    _ensure()
    if not req.patient_id:
        raise HTTPException(status_code=400, detail="patient_id 必填")
    try:
        d = _store.create_account(req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return MemberAccount(**d)


@router.get("/accounts/{account_id}", response_model=MemberAccount)
async def get_account(account_id: str) -> MemberAccount:
    _ensure()
    a = _store.get_account(account_id)
    if a is None:
        raise HTTPException(status_code=404, detail=f"account not found: {account_id}")
    return MemberAccount(**a)


@router.get("/accounts", response_model=AccountList)
async def list_accounts() -> AccountList:
    _ensure()
    items = _store.list_accounts()
    return AccountList(total=len(items), accounts=items)


@router.post("/accounts/{account_id}/recharge", response_model=MemberAccount)
async def recharge(account_id: str, req: RechargeRequest) -> MemberAccount:
    _ensure()
    try:
        a = _store.recharge(account_id, req.amount, req.description or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return MemberAccount(**a)


@router.post("/accounts/{account_id}/consume", response_model=MemberAccount)
async def consume(account_id: str, req: ConsumeRequest) -> MemberAccount:
    _ensure()
    try:
        a = _store.consume(account_id, req.amount, req.description or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return MemberAccount(**a)


@router.get("/accounts/{account_id}/transactions", response_model=TransactionList)
async def list_transactions(account_id: str) -> TransactionList:
    _ensure()
    if _store.get_account(account_id) is None:
        raise HTTPException(status_code=404, detail=f"account not found: {account_id}")
    rows = _store.list_transactions(account_id)
    return TransactionList(total=len(rows), transactions=rows)


@router.get("/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    _ensure()
    s = _store.stats()
    return StatsResponse(
        total_accounts=s["total_accounts"],
        total_balance=s["total_balance"],
        total_recharged=s["total_recharged"],
        total_consumed=s["total_consumed"],
        level_distribution={
            k: LevelStat(count=int(v["count"]), balance=v["balance"])
            for k, v in s["level_distribution"].items()
        },
    )
