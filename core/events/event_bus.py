"""In-process pub/sub EventBus (PRD §18.2).

Designed for single-worker / standalone deployments. For
multi-worker / cloud deployments the platform transparently
swaps in :class:`core.events.redis_bus.RedisEventBus` which
shares the same ``publish`` / ``subscribe`` surface.

Wildcards: subscribers can pass a topic pattern with ``*`` to
match a single level (e.g. ``record.*`` matches ``record.created``).
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, DefaultDict, List, Optional, Set

logger = logging.getLogger(__name__)

Handler = Callable[["Event"], Awaitable[None]]


@dataclass
class Event:
    topic: str
    payload: Any = None
    sender: Optional[str] = None
    correlation_id: Optional[str] = None


@dataclass
class _Subscription:
    topic: str
    handler: Handler
    is_pattern: bool = False


class EventBus:
    """In-process pub/sub.

    Concurrency: a single asyncio lock serialises subscribe /
    unsubscribe, but publishing fans out concurrently to every
    subscriber (each handler runs as its own task).
    """

    def __init__(self) -> None:
        self._handlers: DefaultDict[str, List[Handler]] = defaultdict(list)
        self._pattern_handlers: List[_Subscription] = []
        self._lock = asyncio.Lock()
        self._closed = False

    # ------------------------------------------------------------------ #
    # Subscribe
    # ------------------------------------------------------------------ #

    async def subscribe(self, topic: str, handler: Handler) -> _Subscription:
        if self._closed:
            raise RuntimeError("EventBus is closed")
        async with self._lock:
            is_pattern = "*" in topic
            sub = _Subscription(topic=topic, handler=handler, is_pattern=is_pattern)
            if is_pattern:
                self._pattern_handlers.append(sub)
            else:
                self._handlers[topic].append(handler)
            return sub

    async def unsubscribe(self, sub: _Subscription) -> None:
        async with self._lock:
            if sub.is_pattern:
                try:
                    self._pattern_handlers.remove(sub)
                except ValueError:
                    pass
            else:
                handlers = self._handlers.get(sub.topic)
                if handlers and sub.handler in handlers:
                    handlers.remove(sub.handler)

    # ------------------------------------------------------------------ #
    # Publish
    # ------------------------------------------------------------------ #

    async def publish(self, event: Event) -> int:
        """Dispatch ``event`` to matching subscribers. Returns the count."""

        handlers: List[Handler] = []
        handlers.extend(self._handlers.get(event.topic, []))
        for sub in list(self._pattern_handlers):
            if self._matches(sub.topic, event.topic):
                handlers.append(sub.handler)
        if not handlers:
            return 0
        await asyncio.gather(*(self._safe(h, event) for h in handlers), return_exceptions=True)
        return len(handlers)

    @staticmethod
    async def _safe(handler: Handler, event: Event) -> None:
        try:
            await handler(event)
        except Exception as exc:  # noqa: BLE001
            logger.exception("event handler error on topic=%s: %s", event.topic, exc)

    @staticmethod
    def _matches(pattern: str, topic: str) -> bool:
        # Translate "a.*.c" / "record.*" into a regex.
        regex = re.escape(pattern).replace(r"\*", r"[^.]+")
        return re.fullmatch(regex, topic) is not None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def close(self) -> None:
        self._closed = True
        self._handlers.clear()
        self._pattern_handlers.clear()

    def topics(self) -> Set[str]:
        return set(self._handlers.keys())


# --------------------------------------------------------------------------- #
# Singleton accessor
# --------------------------------------------------------------------------- #


_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus


def set_event_bus(bus: EventBus) -> None:
    global _bus
    _bus = bus


async def reset_event_bus() -> None:
    global _bus
    if _bus is not None:
        await _bus.close()
    _bus = EventBus()
