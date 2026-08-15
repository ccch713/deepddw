"""HRIS 适配器管理器（DDW AI Hub v5.4 — 模块 C2）。

- 注册/获取适配器
- 监听 ``training.session.completed`` / ``training.assessment.completed`` → 自动推送到已启用的 HRIS
- 同步日志（内存）
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from core.events.bus import get_bus
from core.hris_adapters.base import BaseHRISAdapter, HRISError

logger = logging.getLogger(__name__)


class HRISManager:
    """单例。负责：实例化、配置、事件分发、日志。"""

    def __init__(self) -> None:
        self._adapters: Dict[str, BaseHRISAdapter] = {}  # key = "{name}:{tenant_id}"
        self._enabled: Dict[str, bool] = {}
        self._configs: Dict[str, Dict[str, Any]] = {}  # tenant 级
        self._events: Dict[str, List[str]] = {}  # {name: [event1, event2]}
        self._logs: Deque[Dict[str, Any]] = deque(maxlen=500)
        self._lock = asyncio.Lock()
        self._subscribed = False

    # ------------------------------------------------------------------ #
    # 注册 / 实例化
    # ------------------------------------------------------------------ #

    def _key(self, name: str, tenant_id: int) -> str:
        return f"{name}:{tenant_id}"

    def register_adapter_class(self, name: str, adapter_cls: type) -> None:
        """由 :mod:`core.main` 在启动时调用，把适配器类登记进 registry。"""
        if not hasattr(self, "_registry"):
            self._registry: Dict[str, type] = {}
        self._registry[name] = adapter_cls

    def _make(self, name: str, tenant_id: int) -> BaseHRISAdapter:
        cls = getattr(self, "_registry", {}).get(name)
        if cls is None:
            raise ValueError(f"unknown HRIS adapter: {name}")
        cfg = self._configs.get(self._key(name, tenant_id), {})
        return cls(config=cfg, tenant_id=tenant_id)

    async def get_or_create(self, name: str, tenant_id: int) -> BaseHRISAdapter:
        k = self._key(name, tenant_id)
        async with self._lock:
            ad = self._adapters.get(k)
            if ad is None:
                ad = self._make(name, tenant_id)
                self._adapters[k] = ad
            return ad

    # ------------------------------------------------------------------ #
    # 配置 / 启停
    # ------------------------------------------------------------------ #

    def set_config(self, name: str, tenant_id: int, config: Dict[str, Any], enabled: bool = True, events: Optional[List[str]] = None) -> None:
        k = self._key(name, tenant_id)
        self._configs[k] = config or {}
        self._enabled[k] = enabled
        self._events[k] = events or ["training.session.completed", "training.assessment.completed"]
        # 配置变了：清掉旧实例
        if k in self._adapters:
            try:
                asyncio.get_event_loop().create_task(self._adapters[k].close())
            except Exception:  # noqa: BLE001
                pass
            self._adapters.pop(k, None)
        logger.info("hris config updated name=%s tenant=%s enabled=%s", name, tenant_id, enabled)
        self._ensure_subscribed()

    def get_config(self, name: str, tenant_id: int) -> Dict[str, Any]:
        return dict(self._configs.get(self._key(name, tenant_id), {}))

    def is_enabled(self, name: str, tenant_id: int) -> bool:
        return bool(self._enabled.get(self._key(name, tenant_id), False))

    # ------------------------------------------------------------------ #
    # 事件订阅
    # ------------------------------------------------------------------ #

    def _ensure_subscribed(self) -> None:
        if self._subscribed:
            return
        bus = get_bus()
        bus.subscribe("training.session.completed", self._on_training_completed)
        bus.subscribe("training.assessment.completed", self._on_assessment_completed)
        self._subscribed = True
        logger.info("HRIS manager subscribed to training events")

    async def _on_training_completed(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        tenant_id = int(payload.get("tenant_id") or 0)
        if not tenant_id:
            return
        for name in ("kingdee", "wecom", "beisen", "feishu", "dingtalk"):
            if not self.is_enabled(name, tenant_id):
                continue
            if "training.session.completed" not in self._events.get(self._key(name, tenant_id), []):
                continue
            try:
                ad = await self.get_or_create(name, tenant_id)
                ok = await ad.push_training_record(payload)
                self._log(name, tenant_id, "push_training_record", ok, payload)
            except HRISError as e:
                self._log(name, tenant_id, "push_training_record", False, payload, str(e))

    async def _on_assessment_completed(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        tenant_id = int(payload.get("tenant_id") or 0)
        if not tenant_id:
            return
        for name in ("kingdee", "wecom", "beisen", "feishu", "dingtalk"):
            if not self.is_enabled(name, tenant_id):
                continue
            if "training.assessment.completed" not in self._events.get(self._key(name, tenant_id), []):
                continue
            try:
                ad = await self.get_or_create(name, tenant_id)
                ok = await ad.push_assessment_result(payload)
                self._log(name, tenant_id, "push_assessment_result", ok, payload)
            except HRISError as e:
                self._log(name, tenant_id, "push_assessment_result", False, payload, str(e))

    # ------------------------------------------------------------------ #
    # 同步员工
    # ------------------------------------------------------------------ #

    async def sync_employees(self, name: str, tenant_id: int) -> List[Dict[str, Any]]:
        ad = await self.get_or_create(name, tenant_id)
        # 自动 auth（如果未鉴权）
        if not ad.is_configured():
            raise HRISError(f"adapter {name} not configured")
        try:
            await ad.authenticate(ad.config)
        except HRISError as e:
            self._log(name, tenant_id, "authenticate", False, {}, str(e))
            raise
        try:
            data = await ad.sync_employees()
            self._log(name, tenant_id, "sync_employees", True, {"count": len(data)})
            return data
        except HRISError as e:
            self._log(name, tenant_id, "sync_employees", False, {}, str(e))
            raise

    # ------------------------------------------------------------------ #
    # 日志
    # ------------------------------------------------------------------ #

    def _log(self, name: str, tenant_id: int, action: str, ok: bool, payload: Any, error: str = "") -> None:
        self._logs.append({
            "ts": time.time(),
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "name": name,
            "tenant_id": tenant_id,
            "action": action,
            "ok": ok,
            "payload": payload if not ok else {"_": "ok" if ok else "fail"},
            "error": error,
        })

    def get_logs(self, tenant_id: Optional[int] = None, limit: int = 100) -> List[Dict[str, Any]]:
        items = list(self._logs)[-limit:][::-1]
        if tenant_id is not None:
            items = [x for x in items if x["tenant_id"] == tenant_id]
        return items


_manager: Optional[HRISManager] = None


def get_manager() -> HRISManager:
    global _manager
    if _manager is None:
        _manager = HRISManager()
    return _manager


__all__ = ["HRISManager", "get_manager"]
