"""DDW EventBus 升级（SDK §6）

增强 Event：增加 idempotency_key + ttl_seconds（SDK §6.1 要求）。
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Awaitable

log = logging.getLogger(__name__)


@dataclass
class PluginEvent:
    """插件事件（SDK §6.1）。"""
    type: str                          # 点分隔命名空间: "medical.record.created"
    source_plugin: str                 # 发送方插件名
    payload: dict                      # 事件数据
    idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    ttl_seconds: int = 30              # 事件有效期


class EventBus:
    """DDW 事件总线（升级版，对齐 SDK §6.1）。"""

    def __init__(self) -> None:
        self._handlers: dict[str, list[tuple[str, Callable]]] = {}
        self._lock = asyncio.Lock()
        self._seen_keys: dict[str, float] = {}  # 幂等去重

    async def publish(self, event: PluginEvent) -> int:
        """发布事件，返回实际派发的 handler 数量。"""
        # 幂等检查
        if event.idempotency_key in self._seen_keys:
            log.debug("Duplicate event %s, skip", event.idempotency_key)
            return 0
        self._seen_keys[event.idempotency_key] = event.timestamp

        # 清理过期幂等记录
        self._cleanup_seen_keys()

        # 通配符匹配
        delivered = 0
        async with self._lock:
            handlers = list(self._handlers.get(event.type, []))
            for pattern, sub in self._handlers.items():
                if pattern.endswith(".*"):
                    prefix = pattern[:-2]
                    if event.type.startswith(prefix + "."):
                        handlers.extend(sub)

        for plugin_name, handler in handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
                delivered += 1
            except Exception as e:  # noqa: BLE001
                log.error("Handler %s failed: %s", plugin_name, e)
        return delivered

    async def subscribe(
        self,
        plugin_name: str,
        event_type: str,
        handler: Callable[[PluginEvent], Awaitable[None] | None],
    ) -> None:
        """订阅事件。event_type 支持通配符（如 "record.*"）。"""
        async with self._lock:
            self._handlers.setdefault(event_type, []).append((plugin_name, handler))

    def _cleanup_seen_keys(self) -> None:
        """清理过期幂等键。"""
        now = time.time()
        to_del = [
            k for k, ts in self._seen_keys.items()
            if now - ts > 60  # 1 分钟内不重复
        ]
        for k in to_del:
            del self._seen_keys[k]
