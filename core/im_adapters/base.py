"""Abstract base class for IM platform adapters (PRD §9.1).

Production-grade additions:
- Retry with exponential backoff on network errors
- Structured logging for inbound/outbound messages
- Audit logging to im_audit_log table
- Rate limiting (per-chat) for flood protection
- Identity mapping (IM user → DDW user) with TTL cache
"""

from __future__ import annotations

import abc
import asyncio
import hashlib
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 模块级 import（供测试 mock 与函数复用）；session_scope 为 async 上下文管理器
try:
    from core.database.session import session_scope as _db_session_scope
except Exception:  # pragma: no cover - import 失败时降级
    _db_session_scope = None


async def _import_scope():
    """延迟导入兜底（模块级 import 失败时用）。"""
    from core.database.session import session_scope

    return session_scope

# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------

_MAX_RETRIES = 2
_BACKOFF_DELAYS = (1.0, 3.0)  # seconds


async def retry_with_backoff(coro_factory, *, max_retries: int = _MAX_RETRIES) -> Any:
    """Call *coro_factory()* up to *max_retries + 1* times on exception.

    Uses exponential backoff (1 s, 3 s).  Re-raises the last exception if all
    attempts fail.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < max_retries:
                delay = _BACKOFF_DELAYS[attempt] if attempt < len(_BACKOFF_DELAYS) else 3.0
                logger.warning(
                    "retry attempt=%d/%d delay=%.1fs error=%s",
                    attempt + 1,
                    max_retries,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Simple TTL cache (identity mapping)
# ---------------------------------------------------------------------------

class _TTLCache:
    """Minimal in-memory cache with per-entry TTL (seconds)."""

    def __init__(self, ttl: int = 3600) -> None:
        self._ttl = ttl
        self._store: Dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> tuple[bool, Any]:
        entry = self._store.get(key)
        if entry is None:
            return False, None
        ts, value = entry
        if time.monotonic() - ts > self._ttl:
            del self._store[key]
            return False, None
        return True, value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic(), value)


# ---------------------------------------------------------------------------
# Rate limiter (per-chat, sliding window)
# ---------------------------------------------------------------------------

class _RateLimiter:
    """Fixed-window rate limiter: max *max_count* entries per *window_sec* per key."""

    def __init__(self, max_count: int = 10, window_sec: int = 60) -> None:
        self._max = max_count
        self._window = window_sec
        self._buckets: Dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        bucket = self._buckets.setdefault(key, [])
        cutoff = now - self._window
        bucket[:] = [t for t in bucket if t > cutoff]
        if len(bucket) >= self._max:
            return False
        bucket.append(now)
        return True


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------

async def write_audit(
    platform: str,
    direction: str,
    chat_id: str,
    user_id: str,
    content: str,
) -> None:
    """Insert a row into ``im_audit_log`` (best-effort, never raises)."""
    try:
        from sqlalchemy import text

        content_hash = hashlib.sha256(content.encode()).hexdigest()[:64]
        scope = _db_session_scope if _db_session_scope is not None else (await _import_scope())
        async with scope() as session:
            await session.execute(
                text(
                    "INSERT INTO im_audit_log "
                    "(platform, direction, chat_id, user_id, content_hash, created_at) "
                    "VALUES (:p, :d, :c, :u, :h, CURRENT_TIMESTAMP)"
                ),
                {"p": platform, "d": direction, "c": chat_id, "u": user_id, "h": content_hash},
            )
    except Exception:  # noqa: BLE001 — audit must never break the main flow
        logger.debug("audit write failed (non-fatal)", exc_info=True)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class BaseIMAdapter(abc.ABC):
    """Interface every IM adapter (DingTalk / Feishu / WeCom / H5) implements."""

    name: str = "base"

    def __init__(
        self,
        *,
        credentials: Optional[Dict[str, str]] = None,
        require_mention: bool = True,
    ) -> None:
        self.credentials: Dict[str, str] = dict(credentials or {})
        self.require_mention = require_mention
        self._user_cache = _TTLCache(ttl=3600)
        self._rate_limiter = _RateLimiter(max_count=10, window_sec=60)

    # ------------------------------------------------------------------ #
    # Sending
    # ------------------------------------------------------------------ #

    @abc.abstractmethod
    async def send_message(self, chat_id: str, content: str) -> str:
        """Send a plain text message; returns the message id (or empty)."""

    @abc.abstractmethod
    async def send_card(self, chat_id: str, card_data: Dict[str, Any]) -> str:
        """Send a card / structured message; returns the message id."""

    # ------------------------------------------------------------------ #
    # Receiving
    # ------------------------------------------------------------------ #

    @abc.abstractmethod
    async def handle_incoming(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Translate the platform payload into a normalised message dict.

        Returns None when the message should be ignored (e.g. non-@ group
        message when require_mention=True).

        The router in :mod:`core.router.message_router` consumes the
        normalised dict.
        """

    @abc.abstractmethod
    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Fetch user info; return at minimum ``name`` and ``phone``."""

    # ------------------------------------------------------------------ #
    # Identity mapping
    # ------------------------------------------------------------------ #

    async def resolve_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Map an IM platform user_id to a DDW user dict.

        Returns None when mapping fails (Deny-by-Default).
        Cached with TTL 1 h.
        """
        hit, cached = self._user_cache.get(user_id)
        if hit:
            return cached

        try:
            platform_user = await self.get_user_info(user_id)
            if not platform_user or not platform_user.get("name"):
                self._user_cache.set(user_id, None)
                return None
            # Attempt DB lookup by phone or name
            from sqlalchemy import text

            scope = _db_session_scope if _db_session_scope is not None else (await _import_scope())
            async with scope() as session:
                phone = platform_user.get("phone", "")
                if phone:
                    result = await session.execute(
                        text("SELECT id, name, phone, role FROM users WHERE phone = :phone LIMIT 1"),
                        {"phone": phone},
                    )
                    row = result.first()
                    if row:
                        mapped = {"user_id": row[0], "name": row[1], "phone": row[2], "role": row[3]}
                        self._user_cache.set(user_id, mapped)
                        return mapped
            # No match found
            self._user_cache.set(user_id, None)
            return None
        except Exception:  # noqa: BLE001
            logger.debug("resolve_user failed for %s", user_id, exc_info=True)
            self._user_cache.set(user_id, None)
            return None

    # ------------------------------------------------------------------ #
    # Rate limit check
    # ------------------------------------------------------------------ #

    def _check_rate_limit(self, chat_id: str) -> bool:
        """Return True if message is allowed, False if rate-limited."""
        return self._rate_limiter.allow(chat_id)

    # ------------------------------------------------------------------ #
    # Lifecycle (optional)
    # ------------------------------------------------------------------ #

    async def start(self) -> None:  # pragma: no cover
        """Start the long-running connection (e.g. DingTalk Stream WS)."""

    async def stop(self) -> None:  # pragma: no cover
        """Stop the connection cleanly."""

    @staticmethod
    def normalise_text(payload: Dict[str, Any]) -> str:
        """Default extraction: prefer ``text`` then ``content``."""
        for key in ("text", "content", "msg", "message"):
            value = payload.get(key)
            if isinstance(value, str):
                return value
        return ""
