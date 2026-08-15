"""DDW Inventory - 数据模型."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel

CATEGORIES = ("consumable", "equipment", "disposable")
ACTIONS = ("in", "out", "adjust")


class InventoryItem(BaseModel):
    id: Optional[str] = None
    name: str
    category: str
    quantity: int = 0
    unit: str = "个"
    min_quantity: int = 0
    expiry_date: Optional[str] = None
    supplier: Optional[str] = None
    unit_cost: float = 0.0
    location: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class InventoryItemCreate(BaseModel):
    name: str
    category: str
    quantity: int = 0
    unit: str = "个"
    min_quantity: int = 0
    expiry_date: Optional[str] = None
    supplier: Optional[str] = None
    unit_cost: float = 0.0
    location: Optional[str] = None


class InventoryItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    min_quantity: Optional[int] = None
    expiry_date: Optional[str] = None
    supplier: Optional[str] = None
    unit_cost: Optional[float] = None
    location: Optional[str] = None


class StockAction(BaseModel):
    quantity_change: int
    reason: Optional[str] = None
    operator: Optional[str] = None


class InventoryLog(BaseModel):
    id: Optional[str] = None
    item_id: str
    action: str
    quantity_change: int
    reason: Optional[str] = None
    operator: Optional[str] = None
    created_at: Optional[datetime] = None


class ItemList(BaseModel):
    total: int
    items: list[InventoryItem]


class LogList(BaseModel):
    total: int
    logs: list[InventoryLog]


class AlertResponse(BaseModel):
    low_stock: list[InventoryItem]
    expiring_soon: list[InventoryItem]


class HealthResponse(BaseModel):
    plugin: str = "ddw_inventory"
    version: str = "0.1.0"
    status: str = "ok"
    total_items: int = 0
