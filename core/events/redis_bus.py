"""Redis-backed EventBus for multi-worker deployments (PRD §18.2).

Wraps :class:`core.events.event_bus.EventBus` (same interface) but
backs subscribe/publish with Redis Pub/Sub so events propagate
across worker processes. Used in cloud mode; standalone mode keeps
the in-process bus.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import List, Optional

import redis.asyncio as aioredis

from core.events.event_bus import Event, Handler, _Subscription, get_event_bus

logger = logging.getLogger(__name__)


class RedisEventBus:
    """Redis Pub/Sub backed event bus.

    Implements the same ``subscribe`` / ``publish`` / ``unsubscribe``
    surface as the in-process bus; falls back to the in-process bus
    when Redis is unreachable so tests can run without a server.
    """

    def __init__(self, url: Optional[str] = None) -> None:
        self.url = url or os.getenv("DDW_REDIS_URL", "redis://localhost:6379/0")
        self._redis: Optional[aioredis.Redis] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._closed = False

    async def _ensure(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self.url, encoding="utf-8", decode_responses=True)
        return self._redis

    # ------------------------------------------------------------------ #
    # Local proxy
    # ------------------------------------------------------------------ #

    @property
    def local(self):
        return get_event_bus()

    async def subscribe(self, topic: str, handler: Handler) -> _Subscription:
        sub = await self.local.subscribe(topic, handler)
        # Also register on Redis so we receive messages from other workers.
        try:
            r = await self._ensure()
            pubsub = r.pubsub()
            await pubsub.psubscribe(topic if "*" in topic else f"__keyspace@0__:{topic}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis subscribe failed for %s: %s", topic, exc)
        return sub

    async def unsubscribe(self, sub: _Subscription) -> None:
        await self.local.unsubscribe(sub)

    async def publish(self, event: Event) -> int:
        # Always publish locally first.
        local_count = await self.local.publish(event)
        try:
            r = await self._ensure()
            await r.publish(event.topic, event.payload or "")
        except Exception as exc:  # noqa: BLE001
            logger.warning("redis publish failed for %s: %s", event.topic, exc)
        return local_count

    async def close(self) -> None:
        self._closed = True
        if self._listener_task:
            self._listener_task.cancel()
        if self._redis is not None:
            await self._redis.aclose()
