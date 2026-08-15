"""DDW 配置 Hash 变化检测（SDK §5.2）

技术规范 §6.1 补充。
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Awaitable, Callable

log = logging.getLogger(__name__)


def hash_config(cfg: dict) -> str:
    """生成配置 SHA256 指纹（前 16 字符）。"""
    canonical = json.dumps(cfg, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


async def detect_config_change(
    plugin_name: str,
    old_hash: str,
    new_cfg: dict,
    notifier: Callable[[str, dict], Awaitable[None]] | None = None,
) -> tuple[bool, str]:
    """检测配置变化，触发热重载。

    Args:
        plugin_name: 插件名
        old_hash: 之前的 hash
        new_cfg: 新配置
        notifier: 通知回调（plugin_name, {old, new}）

    Returns:
        (changed, new_hash)
    """
    new_hash = hash_config(new_cfg)
    if new_hash == old_hash:
        return False, old_hash

    log.info("Config changed for %s: %s → %s", plugin_name, old_hash, new_hash)
    if notifier is not None:
        await notifier(plugin_name, {"old": old_hash, "new": new_hash})
    return True, new_hash


class ConfigHashStore:
    """配置 Hash 存储（per-plugin）。"""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def set(self, plugin_name: str, hash_value: str) -> None:
        self._store[plugin_name] = hash_value

    def get(self, plugin_name: str) -> str | None:
        return self._store.get(plugin_name)

    async def watch(
        self,
        plugin_name: str,
        new_cfg: dict,
        notifier: Callable[[str, dict], Awaitable[None]],
    ) -> bool:
        """监听某个插件的配置变化。"""
        old = self.get(plugin_name) or ""
        changed, new_hash = await detect_config_change(plugin_name, old, new_cfg, notifier)
        if changed:
            self.set(plugin_name, new_hash)
        return changed
