"""Token / cost usage tracking (PRD §8 / §13).

The :class:`UsageTracker` keeps an in-memory rolling window and a
persistent store on the ``main`` database (``llm_usage_records``).
The DB write is fire-and-forget from the caller's point of view; in
cloud mode the gateway can additionally mirror to Redis.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
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
        self._totals: Dict[str, float] = {
            "tokens_in": 0.0, "tokens_out": 0.0, "cost": 0.0, "calls": 0.0,
        }

    def record(
        self, *, provider: str, model: str, response: ChatResponse,
        ctx: Optional[RouteContext] = None, ok: bool = True,
    ) -> None:
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
            cfg = dep.databases.get("main")
            if cfg is None or getattr(cfg, "engine", "sqlite") != "sqlite":
                return None
            return getattr(cfg, "path", "./data/ddw_main.db")
        except Exception as exc:  # noqa: BLE001
            logger.debug("usage: cannot resolve main db path: %s", exc)
            return None

    def _persist(self, entry: Dict[str, Any], rule: Optional[str]) -> None:
        """Best-effort async insert into ``llm_usage_records``（P0-5）。

        复用全局 AsyncEngine（core.database.session），去掉同步 sqlite3 直连与
        MAX(id)+1 手算主键（表经 LLMUsageRecord ORM 建表，id 由 DB 自增）。
        在运行中的事件循环里调度异步任务；无循环（同步上下文）时跳过落库
        （窗口数据仍保留，绝不阻塞调用方）。
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("usage: no running event loop, skip persist")
            return
        try:
            loop.create_task(_persist_async(entry, rule))
        except Exception as exc:  # noqa: BLE001
            logger.debug("usage: schedule persist failed: %s", exc)

async def _persist_async(entry: Dict[str, Any], rule: Optional[str]) -> None:
    """异步落库（ORM + 全局 AsyncEngine；失败仅 debug 日志）。"""
    try:
        from core.database.models import LLMUsageRecord
        from core.database.session import get_session_maker

        async with get_session_maker()() as session:
            session.add(LLMUsageRecord(
                user_id=None,
                tenant_id=None,
                provider=entry.get("provider", ""),
                model=entry.get("model", ""),
                tokens_in=int(entry.get("tokens_in") or 0),
                tokens_out=int(entry.get("tokens_out") or 0),
                cost=float(entry.get("cost") or 0.0),
                latency_ms=int(entry.get("latency_ms") or 0),
                rule=rule,
                ok=bool(entry.get("ok", True)),
                error=None,
            ))
            await session.commit()
    except Exception as exc:  # noqa: BLE001  # 用量落库失败不阻塞 LLM 调用
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
