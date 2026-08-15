"""DDW Aggregated Pay - 存储."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class AggregatedPayStore:
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
                CREATE TABLE IF NOT EXISTS pay_channels (
                    id TEXT PRIMARY KEY,
                    channel_name TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    config TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pay_transactions (
                    id TEXT PRIMARY KEY,
                    payment_record_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    amount REAL NOT NULL,
                    trade_no TEXT,
                    status TEXT DEFAULT 'pending',
                    reconciled INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tx_pay_record "
                "ON pay_transactions(payment_record_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tx_status "
                "ON pay_transactions(status)"
            )

    # --- channels ---

    def create_channel(self, data: dict[str, Any]) -> dict[str, Any]:
        cid = data.get("id") or f"ch_{uuid.uuid4().hex[:6]}"
        payload = dict(data)
        payload["id"] = cid
        payload.setdefault("is_active", True)
        payload["config"] = json.dumps(payload.get("config", {}), ensure_ascii=False)
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO pay_channels (id, channel_name, is_active, config) VALUES (?, ?, ?, ?)",
                (
                    payload["id"], payload["channel_name"],
                    int(payload["is_active"]), payload["config"],
                ),
            )
        return self.get_channel(cid) or {}

    def get_channel(self, channel_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM pay_channels WHERE id=?", (channel_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["is_active"] = bool(d.get("is_active", 1))
        if d.get("config"):
            try:
                d["config"] = json.loads(d["config"])
            except json.JSONDecodeError:
                d["config"] = {}
        return d

    def list_channels(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM pay_channels ORDER BY channel_name"
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["is_active"] = bool(d.get("is_active", 1))
            if d.get("config"):
                try:
                    d["config"] = json.loads(d["config"])
                except json.JSONDecodeError:
                    d["config"] = {}
            out.append(d)
        return out

    # --- transactions ---

    def create_transaction(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        tid = data.get("id") or f"ptx_{uuid.uuid4().hex[:8]}"
        payload = dict(data)
        payload["id"] = tid
        payload.setdefault("status", "pending")
        payload.setdefault("trade_no", None)
        payload.setdefault("reconciled", False)
        payload["created_at"] = now
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pay_transactions (
                    id, payment_record_id, channel, amount, trade_no,
                    status, reconciled, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"], payload["payment_record_id"], payload["channel"],
                    payload["amount"], payload["trade_no"], payload["status"],
                    int(payload["reconciled"]), payload["created_at"],
                ),
            )
        return self.get_transaction(tid) or {}

    def get_transaction(self, transaction_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM pay_transactions WHERE id=?", (transaction_id,)
            ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["reconciled"] = bool(d.get("reconciled", 0))
        return d

    def list_transactions(
        self, channel: Optional[str] = None, status: Optional[str] = None
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if channel:
            where.append("channel = ?")
            params.append(channel)
        if status:
            where.append("status = ?")
            params.append(status)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM pay_transactions {where_sql} ORDER BY created_at",
                tuple(params),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["reconciled"] = bool(d.get("reconciled", 0))
            out.append(d)
        return out

    def update_transaction(
        self, transaction_id: str, updates: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        if not updates:
            return self.get_transaction(transaction_id)
        if "reconciled" in updates:
            updates["reconciled"] = int(bool(updates["reconciled"]))
        fields = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [transaction_id]
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE pay_transactions SET {fields} WHERE id=?", tuple(values)
            )
        return self.get_transaction(transaction_id)

    def reconcile(self, date: str) -> dict[str, Any]:
        """对账: 比对 ddw_payment 的 paid 记录与本表 success 记录."""
        payment_db = self._find_payment_db()
        if payment_db is None:
            return {
                "date": date,
                "matched": 0,
                "mismatched": [],
                "payment_total": 0.0,
                "transaction_total": 0.0,
                "diff": 0.0,
            }
        # 读取 paid 记录 (同 date)
        payment_rows: list[dict] = []
        try:
            with sqlite3.connect(payment_db, timeout=5) as conn:
                conn.row_factory = sqlite3.Row
                payment_rows = [dict(r) for r in conn.execute(
                    "SELECT id, actual_amount, status FROM payment_records "
                    "WHERE substr(created_at,1,10)=?",
                    (date,),
                ).fetchall()]
        except sqlite3.Error:
            pass
        payment_paid = [r for r in payment_rows if r["status"] == "paid"]
        payment_total = sum(float(r["actual_amount"]) for r in payment_paid)
        # 读取 success 交易 (同 date)
        tx_rows = self.list_transactions(status="success")
        tx_by_record: dict[str, list[dict]] = {}
        for r in tx_rows:
            if (r.get("created_at") or "").startswith(date):
                tx_by_record.setdefault(r["payment_record_id"], []).append(r)
        tx_total = sum(
            float(r["amount"])
            for rs in tx_by_record.values()
            for r in rs
        )
        # 匹配: payment_record_id 在 success 列表中
        matched = 0
        mismatched: list[dict] = []
        for p in payment_paid:
            if p["id"] in tx_by_record:
                # 检查金额一致
                tx_amount = sum(float(t["amount"]) for t in tx_by_record[p["id"]])
                if abs(tx_amount - float(p["actual_amount"])) < 0.01:
                    matched += 1
                else:
                    mismatched.append({
                        "payment_record_id": p["id"],
                        "reason": f"金额不一致: payment={p['actual_amount']}, tx={tx_amount}",
                    })
            else:
                mismatched.append({
                    "payment_record_id": p["id"],
                    "reason": "支付成功但无对应交易",
                })
        # 标记已对账
        for rs in tx_by_record.values():
            for t in rs:
                if (t.get("created_at") or "").startswith(date):
                    self.update_transaction(t["id"], {"reconciled": True})
        return {
            "date": date,
            "matched": matched,
            "mismatched": mismatched,
            "payment_total": round(payment_total, 2),
            "transaction_total": round(tx_total, 2),
            "diff": round(payment_total - tx_total, 2),
        }

    def _find_payment_db(self) -> Optional[Path]:
        for cand in [
            self.db_path.parent / "payment.db",
            self.db_path.parent.parent / "ddw_payment" / "data" / "payment.db",
        ]:
            if cand.exists():
                return cand
        return None

    def total_channels(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM pay_channels").fetchone()[0])

    def total_transactions(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM pay_transactions").fetchone()[0])
