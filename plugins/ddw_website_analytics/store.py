"""DDW Website Analytics - SQLite-backed parsed-result cache (PRD §6.4)."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


SCHEMA = """
CREATE TABLE IF NOT EXISTS aggregate_cache (
    key TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


class AnalyticsStore:
    """Persist the last aggregated payload so cold starts can return instantly.

    Key layout:
      * ``daily``           -> list of daily stats (period-agnostic; 30 days)
      * ``pages``           -> list of page stats (top 20)
      * ``referrers``       -> list of referrer stats
      * ``crawlers``        -> list of crawler stats
      * ``summary::<period>``  -> summary snapshot keyed by period string
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT payload, updated_at FROM aggregate_cache WHERE key=?",
                (key,),
            ).fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row[0])
        except (TypeError, ValueError):
            return None
        return {"data": data, "updated_at": row[1]}

    def set(self, key: str, data: Any) -> None:
        payload = json.dumps(data, default=str, ensure_ascii=False)
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO aggregate_cache(key, payload, updated_at)"
                " VALUES(?, ?, ?)",
                (key, payload, now),
            )

    def last_updated(self) -> Optional[str]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT updated_at FROM aggregate_cache ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        return row[0] if row else None
