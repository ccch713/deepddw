"""DDW Marketing - 存储."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class CampaignStore:
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
                CREATE TABLE IF NOT EXISTS campaigns (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    target_tags TEXT,
                    target_levels TEXT,
                    channel TEXT DEFAULT 'wechat',
                    status TEXT DEFAULT 'draft',
                    scheduled_at TEXT,
                    sent_count INTEGER DEFAULT 0,
                    click_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        cid = data.get("id") or f"camp_{uuid.uuid4().hex[:6]}"
        payload = dict(data)
        payload["id"] = cid
        payload["target_tags"] = json.dumps(payload.get("target_tags", []), ensure_ascii=False)
        payload["target_levels"] = json.dumps(payload.get("target_levels", []), ensure_ascii=False)
        payload.setdefault("status", "draft")
        payload.setdefault("channel", "wechat")
        payload.setdefault("sent_count", 0)
        payload.setdefault("click_count", 0)
        payload.setdefault("scheduled_at", None)
        payload["created_at"] = now
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO campaigns (
                    id, name, content, target_tags, target_levels, channel,
                    status, scheduled_at, sent_count, click_count, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(payload[k] for k in [
                    "id", "name", "content", "target_tags", "target_levels", "channel",
                    "status", "scheduled_at", "sent_count", "click_count", "created_at",
                ]),
            )
        return self.get(cid) or {}

    def get(self, campaign_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM campaigns WHERE id=?", (campaign_id,)
            ).fetchone()
        return self._to_dict(row) if row else None

    def list_all(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM campaigns ORDER BY created_at DESC"
            ).fetchall()
        return [self._to_dict(r) for r in rows]

    def update(
        self, campaign_id: str, updates: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        if not updates:
            return self.get(campaign_id)
        if "target_tags" in updates and isinstance(updates["target_tags"], list):
            updates["target_tags"] = json.dumps(updates["target_tags"], ensure_ascii=False)
        if "target_levels" in updates and isinstance(updates["target_levels"], list):
            updates["target_levels"] = json.dumps(updates["target_levels"], ensure_ascii=False)
        fields = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [campaign_id]
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE campaigns SET {fields} WHERE id=?", tuple(values)
            )
        return self.get(campaign_id)

    def total_count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0])

    @staticmethod
    def _to_dict(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        for k in ("target_tags", "target_levels"):
            v = d.get(k)
            if v is None or v == "":
                d[k] = []
                continue
            try:
                d[k] = json.loads(v)
            except json.JSONDecodeError:
                d[k] = []
        return d
