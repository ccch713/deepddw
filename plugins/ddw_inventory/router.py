"""DDW Inventory - FastAPI router."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from .models import (
    CATEGORIES,
    AlertResponse,
    HealthResponse,
    InventoryItem,
    InventoryItemCreate,
    InventoryItemUpdate,
    ItemList,
    LogList,
    StockAction,
)
from .store import InventoryStore

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/plugins/ddw_inventory", tags=["ddw_inventory"]
)
_store: InventoryStore | None = None


def set_store(s: InventoryStore) -> None:
    global _store
    _store = s


def _ensure() -> None:
    if _store is None:
        raise HTTPException(status_code=503, detail="plugin not initialized")


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    if _store is None:
        return HealthResponse()
    return HealthResponse(total_items=_store.total_count())


@router.post("/items", response_model=InventoryItem, status_code=201)
async def create_item(req: InventoryItemCreate) -> InventoryItem:
    _ensure()
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name 必填")
    if req.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"invalid category: {req.category}")
    if req.quantity < 0:
        raise HTTPException(status_code=400, detail="quantity 不能为负")
    d = _store.create_item(req.model_dump())
    return InventoryItem(**d)


@router.get("/items", response_model=ItemList)
async def list_items(
    category: Optional[str] = None, low_stock: bool = False
) -> ItemList:
    _ensure()
    items = _store.list_items(category=category, low_stock=low_stock)
    return ItemList(total=len(items), items=items)


@router.get("/items/{item_id}", response_model=InventoryItem)
async def get_item(item_id: str) -> InventoryItem:
    _ensure()
    d = _store.get_item(item_id)
    if d is None:
        raise HTTPException(status_code=404, detail=f"item not found: {item_id}")
    return InventoryItem(**d)


@router.patch("/items/{item_id}", response_model=InventoryItem)
async def update_item(item_id: str, req: InventoryItemUpdate) -> InventoryItem:
    _ensure()
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if "category" in updates and updates["category"] not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"invalid category: {updates['category']}")
    d = _store.update_item(item_id, updates)
    if d is None:
        raise HTTPException(status_code=404, detail=f"item not found: {item_id}")
    return InventoryItem(**d)


@router.post("/items/{item_id}/in", response_model=InventoryItem)
async def stock_in(item_id: str, req: StockAction) -> InventoryItem:
    _ensure()
    if req.quantity_change <= 0:
        raise HTTPException(status_code=400, detail="quantity_change 必须 > 0")
    try:
        d = _store.stock_in(item_id, req.quantity_change, req.reason or "采购入库", req.operator or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return InventoryItem(**d)


@router.post("/items/{item_id}/out", response_model=InventoryItem)
async def stock_out(item_id: str, req: StockAction) -> InventoryItem:
    _ensure()
    if req.quantity_change <= 0:
        raise HTTPException(status_code=400, detail="quantity_change 必须 > 0")
    try:
        d = _store.stock_out(item_id, req.quantity_change, req.reason or "领用", req.operator or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return InventoryItem(**d)


@router.post("/items/{item_id}/adjust", response_model=InventoryItem)
async def adjust(item_id: str, new_quantity: int, reason: Optional[str] = None) -> InventoryItem:
    _ensure()
    try:
        d = _store.adjust(item_id, new_quantity, reason or "盘点", "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return InventoryItem(**d)


@router.get("/alerts", response_model=AlertResponse)
async def alerts() -> AlertResponse:
    _ensure()
    a = _store.alerts()
    return AlertResponse(low_stock=a["low_stock"], expiring_soon=a["expiring_soon"])


@router.get("/logs", response_model=LogList)
async def list_logs(item_id: Optional[str] = None) -> LogList:
    _ensure()
    rows = _store.list_logs(item_id=item_id)
    return LogList(total=len(rows), logs=rows)
