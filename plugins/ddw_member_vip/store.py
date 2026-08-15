"""DDW Member VIP - 存储 + 业务逻辑."""
from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .models import RECHARGE_GIFTS, VIP_LEVELS


def _level_for_total(total_recharged: float) -> str:
    """根据累计充值金额返回等级."""
    sorted_levels = sorted(
        VIP_LEVELS.items(),
        key=lambda kv: kv[1]["min_recharge"],
        reverse=True,
    )
    for level, cfg in sorted_levels:
        if total_recharged >= cfg["min_recharge"]:
            return level
    return "normal"


def _discount_for_level(level: str) -> float:
    return VIP_LEVELS.get(level, VIP_LEVELS["normal"])["discount"]


class MemberStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS member_accounts (
                    id TEXT PRIMARY KEY,
                    patient_id TEXT NOT NULL UNIQUE,
                    level TEXT DEFAULT 'normal',
                    balance REAL DEFAULT 0,
                    total_recharged REAL DEFAULT 0,
                    total_consumed REAL DEFAULT 0,
                    discount_rate REAL DEFAULT 1.0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transactions (
                    id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    balance_after REAL NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tx_account "
                "ON transactions(account_id)"
            )

    def create_account(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        aid = data.get("id") or f"mem_{uuid.uuid4().hex[:8]}"
        payload = dict(data)
        payload["id"] = aid
        payload.setdefault("level", "normal")
        payload.setdefault("balance", 0.0)
        payload.setdefault("total_recharged", 0.0)
        payload.setdefault("total_consumed", 0.0)
        payload.setdefault("discount_rate", 1.0)
        payload["created_at"] = now
        payload["updated_at"] = now
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO member_accounts (
                        id, patient_id, level, balance, total_recharged,
                        total_consumed, discount_rate, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        payload["id"], payload["patient_id"], payload["level"],
                        payload["balance"], payload["total_recharged"],
                        payload["total_consumed"], payload["discount_rate"],
                        payload["created_at"], payload["updated_at"],
                    ),
                )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"该患者已有会员账户: {payload['patient_id']}") from e
        return self.get_account(aid) or {}

    def get_account(self, account_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM member_accounts WHERE id=?", (account_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_by_patient(self, patient_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM member_accounts WHERE patient_id=?",
                (patient_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_accounts(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM member_accounts ORDER BY total_recharged DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def update_account(
        self, account_id: str, updates: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        if not updates:
            return self.get_account(account_id)
        fields = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [account_id]
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE member_accounts SET {fields} WHERE id=?", tuple(values)
            )
        return self.get_account(account_id)

    def recharge(self, account_id: str, amount: float, description: str = "") -> dict[str, Any]:
        if amount <= 0:
            raise ValueError("充值金额必须 > 0")
        acc = self.get_account(account_id)
        if acc is None:
            raise ValueError(f"账户不存在: {account_id}")
        # 命中赠送规则
        gift = RECHARGE_GIFTS.get(int(amount), 0) if int(amount) in RECHARGE_GIFTS else 0
        total_in = amount + gift
        new_balance = acc["balance"] + total_in
        new_total_recharged = acc["total_recharged"] + amount  # 累计充值不算赠送
        new_level = _level_for_total(new_total_recharged)
        new_discount = _discount_for_level(new_level)
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE member_accounts
                SET balance=?, total_recharged=?, level=?,
                    discount_rate=?, updated_at=?
                WHERE id=?
                """,
                (new_balance, new_total_recharged, new_level,
                 new_discount, now, account_id),
            )
            # 充值交易
            conn.execute(
                """
                INSERT INTO transactions
                (id, account_id, type, amount, balance_after, description, created_at)
                VALUES (?, ?, 'recharge', ?, ?, ?, ?)
                """,
                (f"tx_{uuid.uuid4().hex[:8]}", account_id, amount,
                 new_balance, description or "用户充值", now),
            )
            # 赠送交易
            if gift > 0:
                conn.execute(
                    """
                    INSERT INTO transactions
                    (id, account_id, type, amount, balance_after, description, created_at)
                    VALUES (?, ?, 'gift', ?, ?, ?, ?)
                    """,
                    (f"tx_{uuid.uuid4().hex[:8]}", account_id, float(gift),
                     new_balance, f"充值赠送(+{gift})", now),
                )
        return self.get_account(account_id) or {}

    def consume(self, account_id: str, amount: float, description: str = "") -> dict[str, Any]:
        if amount <= 0:
            raise ValueError("消费金额必须 > 0")
        acc = self.get_account(account_id)
        if acc is None:
            raise ValueError(f"账户不存在: {account_id}")
        if acc["balance"] < amount:
            raise ValueError(f"余额不足: 当前 {acc['balance']}, 消费 {amount}")
        new_balance = acc["balance"] - amount
        new_total_consumed = acc["total_consumed"] + amount
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE member_accounts
                SET balance=?, total_consumed=?, updated_at=?
                WHERE id=?
                """,
                (new_balance, new_total_consumed, now, account_id),
            )
            conn.execute(
                """
                INSERT INTO transactions
                (id, account_id, type, amount, balance_after, description, created_at)
                VALUES (?, ?, 'consume', ?, ?, ?, ?)
                """,
                (f"tx_{uuid.uuid4().hex[:8]}", account_id, amount,
                 new_balance, description or "消费扣款", now),
            )
        return self.get_account(account_id) or {}

    def list_transactions(self, account_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM transactions WHERE account_id=? ORDER BY created_at DESC",
                (account_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        accounts = self.list_accounts()
        level_dist: dict[str, dict[str, float]] = {}
        total_balance = 0.0
        total_recharged = 0.0
        total_consumed = 0.0
        for a in accounts:
            lv = a["level"]
            if lv not in level_dist:
                level_dist[lv] = {"count": 0, "balance": 0.0}
            level_dist[lv]["count"] += 1
            level_dist[lv]["balance"] += a["balance"]
            total_balance += a["balance"]
            total_recharged += a["total_recharged"]
            total_consumed += a["total_consumed"]
        return {
            "total_accounts": len(accounts),
            "total_balance": round(total_balance, 2),
            "total_recharged": round(total_recharged, 2),
            "total_consumed": round(total_consumed, 2),
            "level_distribution": level_dist,
        }

    def total_accounts(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM member_accounts").fetchone()[0])
