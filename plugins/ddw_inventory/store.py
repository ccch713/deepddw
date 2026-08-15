"""DDW Inventory - 存储."""
from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


class InventoryStore:
    EXPIRY_ALERT_DAYS = 30

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS inventory_items (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    quantity INTEGER DEFAULT 0,
                    unit TEXT DEFAULT '个',
                    min_quantity INTEGER DEFAULT 0,
                    expiry_date TEXT,
                    supplier TEXT,
                    unit_cost REAL DEFAULT 0,
                    location TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS inventory_logs (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    quantity_change INTEGER NOT NULL,
                    reason TEXT,
                    operator TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_logs_item "
                "ON inventory_logs(item_id)"
            )

    def create_item(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        iid = data.get("id") or f"inv_{uuid.uuid4().hex[:6]}"
        payload = dict(data)
        payload["id"] = iid
        payload.setdefault("unit", "个")
        payload.setdefault("min_quantity", 0)
        payload.setdefault("unit_cost", 0.0)
        payload["created_at"] = now
        payload["updated_at"] = now
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO inventory_items (
                    id, name, category, quantity, unit, min_quantity,
                    expiry_date, supplier, unit_cost, location,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(payload[k] for k in [
                    "id", "name", "category", "quantity", "unit", "min_quantity",
                    "expiry_date", "supplier", "unit_cost", "location",
                    "created_at", "updated_at",
                ]),
            )
        return self.get_item(iid) or {}

    def get_item(self, item_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM inventory_items WHERE id=?", (item_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_items(
        self,
        category: Optional[str] = None,
        low_stock: bool = False,
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM inventory_items WHERE category=? ORDER BY name",
                    (category,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM inventory_items ORDER BY name"
                ).fetchall()
        items = [dict(r) for r in rows]
        if low_stock:
            items = [it for it in items if it["quantity"] <= it["min_quantity"]]
        return items

    def update_item(
        self, item_id: str, updates: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        if not updates:
            return self.get_item(item_id)
        updates["updated_at"] = datetime.now(timezone.utc).isoformat()
        fields = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [item_id]
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE inventory_items SET {fields} WHERE id=?", tuple(values)
            )
        return self.get_item(item_id)

    def stock_in(
        self, item_id: str, quantity: int, reason: str = "采购入库", operator: str = ""
    ) -> dict[str, Any]:
        return self._stock_change(item_id, quantity, "in", reason, operator)

    def stock_out(
        self, item_id: str, quantity: int, reason: str = "领用", operator: str = ""
    ) -> dict[str, Any]:
        return self._stock_change(item_id, -abs(quantity), "out", reason, operator)

    def adjust(
        self, item_id: str, new_quantity: int, reason: str = "盘点", operator: str = ""
    ) -> dict[str, Any]:
        item = self.get_item(item_id)
        if item is None:
            raise ValueError(f"item not found: {item_id}")
        delta = new_quantity - item["quantity"]
        return self._stock_change(item_id, delta, "adjust", reason, operator)

    def _stock_change(
        self,
        item_id: str,
        delta: int,
        action: str,
        reason: str,
        operator: str,
    ) -> dict[str, Any]:
        item = self.get_item(item_id)
        if item is None:
            raise ValueError(f"item not found: {item_id}")
        if delta == 0:
            return item
        new_qty = item["quantity"] + delta
        if new_qty < 0:
            raise ValueError(
                f"库存不足: 当前 {item['quantity']}, 变更 {delta}"
            )
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE inventory_items SET quantity=?, updated_at=? WHERE id=?",
                (new_qty, now, item_id),
            )
            log_id = f"log_{uuid.uuid4().hex[:8]}"
            conn.execute(
                """
                INSERT INTO inventory_logs (
                    id, item_id, action, quantity_change, reason, operator, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (log_id, item_id, action, delta, reason, operator, now),
            )
        return self.get_item(item_id) or {}

    def list_logs(self, item_id: Optional[str] = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if item_id:
                rows = conn.execute(
                    "SELECT * FROM inventory_logs WHERE item_id=? ORDER BY created_at DESC",
                    (item_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM inventory_logs ORDER BY created_at DESC"
                ).fetchall()
        return [dict(r) for r in rows]

    def alerts(self) -> dict[str, list[dict[str, Any]]]:
        items = self.list_items()
        low = [it for it in items if it["quantity"] <= it["min_quantity"]]
        today = datetime.now(timezone.utc).date()
        threshold = today + timedelta(days=self.EXPIRY_ALERT_DAYS)
        expiring: list[dict[str, Any]] = []
        for it in items:
            exp = it.get("expiry_date")
            if not exp:
                continue
            try:
                d = datetime.strptime(exp, "%Y-%m-%d").date()  # noqa: DTZ007
            except ValueError:
                continue
            if today <= d <= threshold:
                expiring.append(it)
        return {"low_stock": low, "expiring_soon": expiring}

    def total_count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM inventory_items").fetchone()[0])
