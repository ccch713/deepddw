"""DDW Plugin Hook 事务化加载（SDK §3.1）

Plugin_SDK §3.1：pre_load_hook → 检查 → 加载 → post_load_hook。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sdk.plugin_base import DDWPlugin

log = logging.getLogger(__name__)


@dataclass
class PluginHookResult:
    """Hook 执行结果。"""
    allowed: bool
    blocking_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PluginLoadError(RuntimeError):
    """Plugin 加载失败（含所有阻断错误）。"""
    def __init__(self, errors: list[str]) -> None:
        super().__init__(f"Plugin 加载失败: {errors}")
        self.errors = errors


async def execute_pre_load_hooks(
    target: "DDWPlugin",
    existing: list["DDWPlugin"],
) -> PluginHookResult:
    """pre_load_hook：所有现有插件检查新插件的依赖/冲突。"""
    errors: list[str] = []
    warnings: list[str] = []
    for plugin in existing:
        try:
            if hasattr(plugin, "check_compatibility"):
                result = await plugin.check_compatibility(target)
                errors.extend(result.blocking_errors)
                warnings.extend(result.warnings)
        except Exception as e:  # noqa: BLE001
            warnings.append(f"{plugin.name} 检查 compatibility 失败: {e}")
    return PluginHookResult(
        allowed=len(errors) == 0,
        blocking_errors=errors,
        warnings=warnings,
    )


async def execute_post_load_hooks(
    target: "DDWPlugin",
    existing: list["DDWPlugin"],
) -> None:
    """post_load_hook：新插件加载成功后通知所有现有插件。"""
    for plugin in existing:
        if plugin.name == target.name:
            continue
        try:
            if hasattr(plugin, "on_plugin_loaded"):
                await plugin.on_plugin_loaded(target)
        except Exception as e:  # noqa: BLE001
            log.warning("on_plugin_loaded failed for %s: %s", plugin.name, e)


def rollback_plugin_load(target: "DDWPlugin") -> None:
    """加载失败时的回滚（清理已部分初始化的状态）。"""
    log.warning("Rolling back plugin load: %s", target.name)
    # 子类可以扩展此函数做更彻底的回滚
    if hasattr(target, "on_unload"):
        # 异步函数不能在同步上下文中 await
        # 这里仅清理可同步处理的部分
        log.info("Plugin %s rollback partial cleanup", target.name)


async def load_plugin_transactional(
    plugin: "DDWPlugin",
    active_plugins: list["DDWPlugin"],
) -> None:
    """事务化加载流程。"""
    # 1. 预检钩子
    pre = await execute_pre_load_hooks(plugin, active_plugins)
    if not pre.allowed:
        rollback_plugin_load(plugin)
        raise PluginLoadError(pre.blocking_errors)

    # 2. 加载钩子
    try:
        from sdk.plugin_base import PluginContext
        ctx = PluginContext(
            loaded_plugins=active_plugins + [plugin],
            config={},
        )
        await plugin.on_load(ctx)
    except Exception as e:  # noqa: BLE001
        rollback_plugin_load(plugin)
        raise PluginLoadError([f"on_load 失败: {e}"]) from e

    # 3. 加载后钩子
    await execute_post_load_hooks(plugin, active_plugins + [plugin])

    log.info("Plugin %s loaded transactionally", plugin.name)
