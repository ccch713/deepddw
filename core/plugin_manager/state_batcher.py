"""DDW Plugin 状态批量推送（SDK §4.1）

Plugin_SDK §4.1：16ms 批量窗口，合并多个插件状态变更，一次推送。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from sdk.plugin_state import PluginStateInfo

log = logging.getLogger(__name__)

# 16ms 批量窗口
_BATCH_WINDOW = 0.016


class PluginStateBatcher:
    """状态批量推送器。"""

    def __init__(self, on_flush: Callable[[dict[str, PluginStateInfo]], Awaitable[None]] | None = None) -> None:
        self._pending: dict[str, PluginStateInfo] = {}
        self._timer: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._on_flush = on_flush or self._default_flush

    async def _default_flush(self, events: dict[str, PluginStateInfo]) -> None:
        log.info("Plugin state batch flush: %d plugins", len(events))

    async def update_state(self, name: str, info: PluginStateInfo) -> None:
        """更新状态。16ms 内的多次更新合并推送。"""
        async with self._lock:
            self._pending[name] = info
            if self._timer is None:
                self._timer = asyncio.create_task(self._flush_after(_BATCH_WINDOW))

    async def _flush_after(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            async with self._lock:
                events = dict(self._pending)
                self._pending.clear()
                self._timer = None
            await self._on_flush(events)
        except asyncio.CancelledError:
            pass
        except Exception as e:  # noqa: BLE001
            log.error("State batch flush failed: %s", e)

    async def flush_now(self) -> None:
        """立即刷新（用于关闭前）。"""
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        async with self._lock:
            events = dict(self._pending)
            self._pending.clear()
        if events:
            await self._on_flush(events)
