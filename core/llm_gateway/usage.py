"""Token / cost usage tracking (PRD §8 / §13).

The :class:`UsageTracker` keeps an in-memory rolling window and a
persistent store on the ``main`` database (``llm_usage_records``).
The DB write is fire-and-forget from the caller's point of view; in
cloud mode the gateway can additionally mirror to Redis.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections import deque
from datetime import datetime
from typing import Any, Deque, Dict, Optional

from core.config import get_deployment
from core.llm_gateway.base import ChatResponse, RouteContext

logger = logging.getLogger(__name__)


class UsageTracker:
    """In-process rolling window of LLM usage.

    The persistent record is created by the gateway API layer
    (see ``core.api``) so that this module does not need an async
    DB session injected everywhere.
    """

    def __init__(self, window_size: int = 1000) -> None:
        self._window: Deque[Dict[str, float]] = deque(maxlen=window_size)
        self._lock = threading.Lock()
        self._totals: Dict[str, float] = {"tokens_in": 0.0, "tokens_out": 0.0, "cost": 0.0, "calls": 0.0}

    def record(self, *, provider: str, model: str, response: ChatResponse, ctx: Optional[RouteContext] = None, ok: bool = True) -> None:
        entry = {
            "provider": provider,
            "model": model,
            "tokens_in": response.tokens_in,
            "tokens_out": response.tokens_out,
            "cost": response.cost,
            "latency_ms": response.latency_ms,
            "ok": ok,
        }
        with self._lock:
            self._window.append(entry)
            self._totals["tokens_in"] += response.tokens_in
            self._totals["tokens_out"] += response.tokens_out
            self._totals["cost"] += response.cost
            self._totals["calls"] += 1
        # Fire-and-forget persist to main DB (llm_usage_records).
        rule = ctx.rule if ctx else None
        self._persist(entry, rule)

    # ------------------------------------------------------------------ #
    # Persistence (sqlite sync write — non-blocking, best effort)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _main_db_path() -> Optional[str]:
        try:
            dep = get_deployment()
            cfg = dep.databases.get("main", {})
            if cfg.get("engine") != "sqlite":
                return None
            return cfg.get("path", "./data/ddw_main.db")
        except Exception as exc:  # noqa: BLE001
            logger.debug("usage: cannot resolve main db path: %s", exc)
            return None

    def _persist(self, entry: Dict[str, Any], rule: Optional[str]) -> None:
        """Best-effort insert into ``llm_usage_records`` (never blocks callers)."""
        path = self._main_db_path()
        if not path:
            return
        try:
            now = datetime.now().isoformat()
            con = sqlite3.connect(path, timeout=5)
            try:
                cur = con.cursor()
                # 历史表 id 为 BIGINT NOT NULL + PRIMARY KEY（非自增），显式取 MAX+1。
                cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM llm_usage_records")
                next_id = cur.fetchone()[0]
                cur.execute(
                    "INSERT INTO llm_usage_records "
                    "(id, user_id, provider, model, tokens_in, tokens_out, cost, latency_ms, "
                    " rule, ok, error, created_at, updated_at, tenant_id) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        next_id,
                        None,
                        entry["provider"],
                        entry["model"],
                        entry["tokens_in"],
                        entry["tokens_out"],
                        entry["cost"],
                        entry["latency_ms"],
                        rule,
                        1 if entry["ok"] else 0,
                        None,
                        now,
                        now,
                        None,
                    ),
                )
                con.commit()
            finally:
                con.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug("usage persist failed: %s", exc)

    def summary(self) -> Dict[str, float]:
        with self._lock:
            return dict(self._totals)

    def recent(self, limit: int = 50) -> list:
        with self._lock:
            return list(self._window)[-limit:]

    def reset(self) -> None:
        with self._lock:
            self._window.clear()
            for k in self._totals:
                self._totals[k] = 0.0
