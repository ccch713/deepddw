"""DDW 进程内 EventBus（轻量 pub/sub）— SDK v2 增强。

v2 增强（参照 Proma 的事件冒泡设计）：
  * Dead Letter Queue（DLQ）：失败的事件处理器自动入队，支持重试和查询
  * 事件元数据：每次 publish 返回 PublishResult，包含成功/失败/耗时
  * 通配符订阅：``subscribe("training.*", cb)`` 匹配 ``training.session.completed``
  * 发布来源追踪：publish 支持 ``source`` 参数标记事件来源插件
  * 事件历史环形缓冲区（可配置大小，默认关闭）

兼容性：``subscribe`` / ``publish`` / ``reset`` 签名不变，已有代码零改动。

事件命名约定（与 modules C/E 配套）：
- ``training.session.completed``
- ``training.assessment.completed``
- ``hris.sync.completed``
- ``plugin.{name}.loaded``
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import (
    Any,
    Awaitable,
    Callable,
    DefaultDict,
    Deque,
    List,
    Optional,
    Union,
)

logger = logging.getLogger(__name__)

Callback = Union[Callable[[Any], Awaitable[None]], Callable[[Any], None]]


# --------------------------------------------------------------------------- #
#  数据结构
# --------------------------------------------------------------------------- #


@dataclass
class HandlerResult:
    """单个事件处理器的执行结果。"""
    callback_name: str
    success: bool
    duration_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class PublishResult:
    """publish() 的返回值：聚合所有处理器的执行结果。"""
    event: str
    source: str = ""
    total_handlers: int = 0
    success_count: int = 0
    failure_count: int = 0
    duration_ms: float = 0.0
    handler_results: List[HandlerResult] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return self.failure_count == 0


@dataclass
class DeadLetter:
    """Dead Letter Queue 条目。"""
    event: str
    payload: Any
    callback_name: str
    error: str
    retry_count: int = 0
    first_failure_at: float = field(default_factory=time.time)
    last_failure_at: float = field(default_factory=time.time)


@dataclass
class EventRecord:
    """事件历史环形缓冲区条目。"""
    event: str
    source: str
    payload_type: str
    handler_count: int
    success: bool
    timestamp: float = field(default_factory=time.time)


# --------------------------------------------------------------------------- #
#  EventBus
# --------------------------------------------------------------------------- #


class EventBus:
    """进程内 pub/sub 事件总线（v2 增强版）。

    兼容 v1 接口：
        bus.subscribe("event", callback)
        await bus.publish("event", payload)
        bus.reset()

    v2 新增：
        bus.subscribe("training.*", callback)   # 通配符
        result = await bus.publish("event", payload, source="ddw-training")
        bus.dlq_retry("event")                  # 重试失败的事件
        bus.dlq_list()                          # 查看 Dead Letter Queue
    """

    def __init__(self, *, history_size: int = 0, max_dlq_size: int = 200) -> None:
        self._subs: DefaultDict[str, List[Callback]] = defaultdict(list)
        self._lock = threading.Lock()

        # v2: Dead Letter Queue
        self._dlq: Deque[DeadLetter] = deque(maxlen=max_dlq_size)
        self._dlq_lock = threading.Lock()

        # v2: 事件历史（环形缓冲区，默认关闭）
        self._history_enabled = history_size > 0
        self._history: Deque[EventRecord] = deque(maxlen=max(0, history_size))
        self._history_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    #  订阅（v1 兼容 + v2 通配符）
    # ------------------------------------------------------------------ #

    def subscribe(self, event: str, callback: Callback) -> None:
        """订阅事件。支持通配符后缀 ``.*``（如 ``training.*`` 匹配所有 training 子事件）。"""
        with self._lock:
            self._subs[event].append(callback)
        logger.debug("subscribed to %s: %s", event, getattr(callback, "__name__", repr(callback)))

    def unsubscribe(self, event: str, callback: Callback) -> None:
        with self._lock:
            if callback in self._subs.get(event, []):
                self._subs[event].remove(callback)

    def listeners(self, event: str) -> List[Callback]:
        """返回匹配事件名的所有订阅者（精确匹配 + 通配符匹配）。"""
        exact = list(self._subs.get(event, []))
        # 通配符匹配：查找 "prefix.*" 形式的订阅
        wildcard_matches: List[Callback] = []
        with self._lock:
            for pattern, cbs in self._subs.items():
                if pattern == event:
                    continue  # 已在 exact 中
                if pattern.endswith(".*") and event.startswith(pattern[:-2] + "."):
                    wildcard_matches.extend(cbs)
        return exact + wildcard_matches

    def listener_count(self, event: str) -> int:
        """返回事件的订阅者数量（含通配符）。"""
        return len(self.listeners(event))

    # ------------------------------------------------------------------ #
    #  发布（v1 兼容 + v2 结果收集）
    # ------------------------------------------------------------------ #

    async def publish(self, event: str, payload: Any = None, *, source: str = "") -> PublishResult:
        """异步发布事件；所有订阅者并发触发。

        Returns:
            PublishResult 包含每个处理器的成功/失败和耗时。
            调用方可忽略返回值（v1 兼容：await bus.publish(...) 不受影响）。
        """
        start = time.monotonic()
        cbs = self.listeners(event)

        async def _run_one(cb):
            """单个 handler（P1-16：隔离失败，供 asyncio.gather 并发执行）。"""
            cb_name = getattr(cb, "__name__", repr(cb))
            cb_start = time.monotonic()
            try:
                if inspect.iscoroutinefunction(cb):
                    await cb(payload)
                else:
                    await asyncio.get_running_loop().run_in_executor(None, cb, payload)
                duration = (time.monotonic() - cb_start) * 1000
                return HandlerResult(callback_name=cb_name, success=True, duration_ms=duration)
            except Exception as exc:  # noqa: BLE001  # 单 handler 失败不影响其他
                duration = (time.monotonic() - cb_start) * 1000
                return HandlerResult(
                    callback_name=cb_name, success=False,
                    duration_ms=duration, error=str(exc),
                )

        # P1-16：同事件多 handler 并发执行（原串行；一个失败不再拖慢/阻断其余）
        results: List[HandlerResult] = list(
            await asyncio.gather(*[_run_one(cb) for cb in cbs])
        )
        success_count = sum(1 for r in results if r.success)
        failure_count = len(results) - success_count
        for r in results:
            if not r.success:
                # 入 Dead Letter Queue（并发执行后统一收尾）
                self._enqueue_dead_letter(event, payload, r.callback_name, r.error or "")
                logger.exception(
                    "event handler '%s' failed for '%s'", r.callback_name, event
                )

        total_duration = (time.monotonic() - start) * 1000
        publish_result = PublishResult(
            event=event,
            source=source,
            total_handlers=len(cbs),
            success_count=success_count,
            failure_count=failure_count,
            duration_ms=total_duration,
            handler_results=results,
        )

        # 记录事件历史
        if self._history_enabled:
            self._record_event(event, source, payload, len(cbs), failure_count == 0)

        return publish_result

    def publish_threadsafe(self, event: str, payload: Any = None, *, source: str = "") -> None:
        """从同步上下文发布（启动一个 task）。"""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.publish(event, payload, source=source))
        except RuntimeError:
            # 无事件循环（同步上下文）：退化到线程
            threading.Thread(
                target=lambda: asyncio.run(self.publish(event, payload, source=source)),
                daemon=True,
            ).start()

    # ------------------------------------------------------------------ #
    #  Dead Letter Queue（v2 新增）
    # ------------------------------------------------------------------ #

    def _enqueue_dead_letter(self, event: str, payload: Any, callback_name: str, error: str) -> None:
        now = time.time()
        with self._dlq_lock:
            # 如果同事件+同回调已有条目，合并（增加 retry_count）
            for dl in self._dlq:
                if dl.event == event and dl.callback_name == callback_name:
                    dl.retry_count += 1
                    dl.last_failure_at = now
                    dl.error = error
                    return
            self._dlq.append(DeadLetter(
                event=event, payload=payload, callback_name=callback_name, error=error,
            ))

    def dlq_list(self) -> List[DeadLetter]:
        """列出 Dead Letter Queue 中的所有条目。"""
        with self._dlq_lock:
            return list(self._dlq)

    def dlq_count(self) -> int:
        return len(self._dlq)

    def dlq_clear(self) -> int:
        """清空 Dead Letter Queue，返回清除的条数。"""
        with self._dlq_lock:
            count = len(self._dlq)
            self._dlq.clear()
            return count

    async def dlq_retry(self, event: Optional[str] = None) -> PublishResult:
        """重试 Dead Letter Queue 中的失败事件。

        Args:
            event: 如果指定，只重试该事件的 DLQ 条目；否则重试全部。

        Returns:
            聚合的 PublishResult。
        """
        with self._dlq_lock:
            if event:
                items = [dl for dl in self._dlq if dl.event == event]
            else:
                items = list(self._dlq)

        start = time.monotonic()
        results: List[HandlerResult] = []
        success_count = 0
        failure_count = 0
        retried_events: set = set()

        for dl in items:
            cb_name = dl.callback_name
            # 找到原始回调
            cbs = self.listeners(dl.event)
            matched_cb = None
            for cb in cbs:
                if getattr(cb, "__name__", repr(cb)) == cb_name:
                    matched_cb = cb
                    break
            if matched_cb is None:
                results.append(HandlerResult(
                    callback_name=cb_name, success=False, error="callback not found (unsubscribed?)",
                ))
                failure_count += 1
                continue

            cb_start = time.monotonic()
            try:
                if inspect.iscoroutinefunction(matched_cb):
                    await matched_cb(dl.payload)
                else:
                    await asyncio.get_running_loop().run_in_executor(None, matched_cb, dl.payload)
                duration = (time.monotonic() - cb_start) * 1000
                results.append(HandlerResult(callback_name=cb_name, success=True, duration_ms=duration))
                success_count += 1
                retried_events.add((dl.event, dl.callback_name))
            except Exception as exc:
                duration = (time.monotonic() - cb_start) * 1000
                results.append(HandlerResult(
                    callback_name=cb_name, success=False, duration_ms=duration, error=str(exc),
                ))
                failure_count += 1

        # 成功重试的条目从 DLQ 移除
        if retried_events:
            with self._dlq_lock:
                self._dlq = deque(
                    dl for dl in self._dlq
                    if (dl.event, dl.callback_name) not in retried_events
                )

        total_duration = (time.monotonic() - start) * 1000
        return PublishResult(
            event=event or "*",
            source="dlq-retry",
            total_handlers=len(items),
            success_count=success_count,
            failure_count=failure_count,
            duration_ms=total_duration,
            handler_results=results,
        )

    # ------------------------------------------------------------------ #
    #  事件历史（v2 新增，默认关闭）
    # ------------------------------------------------------------------ #

    def _record_event(self, event: str, source: str, payload: Any, handler_count: int, success: bool) -> None:
        with self._history_lock:
            self._history.append(EventRecord(
                event=event,
                source=source,
                payload_type=type(payload).__name__,
                handler_count=handler_count,
                success=success,
            ))

    def history(self, limit: int = 20) -> List[EventRecord]:
        """返回最近的事件历史（需 history_size > 0 时启用）。"""
        with self._history_lock:
            return list(self._history)[-limit:]

    def history_clear(self) -> None:
        with self._history_lock:
            self._history.clear()

    # ------------------------------------------------------------------ #
    #  生命周期
    # ------------------------------------------------------------------ #

    def reset(self) -> None:
        """清空所有订阅、DLQ 和历史（测试 / 重载用）。"""
        with self._lock:
            self._subs.clear()
        with self._dlq_lock:
            self._dlq.clear()
        with self._history_lock:
            self._history.clear()


# 全局单例
_bus: EventBus = EventBus()


def get_bus() -> EventBus:
    return _bus


__all__ = [
    "EventBus", "get_bus",
    "PublishResult", "HandlerResult", "DeadLetter", "EventRecord",
]
