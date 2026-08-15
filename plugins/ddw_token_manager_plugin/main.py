"""
DDW Token Manager 插件入口

继承 SDK PluginBase，使用 SDK PluginState 状态机。

修复清单 (v5.7 §28):
1. 移除自定义 DDWPluginBase → 继承 sdk.plugin_base.PluginBase
2. 移除自定义 PluginState → 使用 sdk.plugin_state.PluginState
3. 实现 PluginBase.setup() 钩子（替代 on_enable）
4. 使用 ConfigManager 管理配置
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from fastapi import FastAPI

# [v5.7修复] 导入 SDK 标准基类
try:
    from sdk.plugin_base import PluginBase
    from sdk.plugin_state import PluginState, PluginStateInfo
except ImportError:
    # 独立运行时（非 SDK 包导入）提供最小兼容桩
    from enum import Enum

    class PluginState(str, Enum):  # type: ignore[no-redef]
        """插件状态（SDK 兼容桩）"""
        LOADING = "loading"
        ACTIVE = "active"
        FAILED = "failed"
        DISABLED = "disabled"
        NEEDS_UPDATE = "needs_update"

    class PluginStateInfo:  # type: ignore[no-redef]
        """SDK 兼容桩"""
        def __init__(self, state: Any, name: str, version: str, **kw: Any) -> None:
            self.state = state
        def to_active(self) -> None:
            self.state = PluginState.ACTIVE
        def to_failed(self, code: int, message: str) -> None:
            self.state = PluginState.FAILED

    from fastapi import APIRouter  # noqa: F811

    class PluginBase:  # type: ignore[no-redef]
        """DDW 插件 ABC 基类（SDK 兼容桩）"""
        name: str = "unnamed-plugin"
        version: str = "0.1.0"
        router_prefix: str = ""

        def __init__(self, app: Any = None, config: Optional[Dict[str, Any]] = None,
                     manifest: Optional[Dict[str, Any]] = None) -> None:
            self.app = app
            self.manifest = dict(manifest or {})
            self.router = APIRouter()
            self.config = dict(config or {})
            self.setup()

        def setup(self) -> None:
            pass

        def register(self) -> None:
            if self.app is not None:
                self.app.include_router(self.router)

logger = logging.getLogger(__name__)


class TokenManagerPlugin(PluginBase):
    """
    DDW Token Manager 插件

    [v5.7修复] 继承 SDK PluginBase，而非自定义 DDWPluginBase

    状态机（使用 SDK PluginState）:
    LOADING → ACTIVE → FAILED / DISABLED / NEEDS_UPDATE
    """
    name = "ddw-token-manager"
    version = "0.1.0"
    router_prefix = "/api/v1/plugins/ddw-token-manager"

    def __init__(
        self,
        app: Optional[FastAPI] = None,
        config: Optional[Dict[str, Any]] = None,
        manifest: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._state_info = PluginStateInfo(
            state=PluginState.LOADING,
            name=self.name,
            version=self.version,
        )
        self._started_at: Optional[float] = None
        self._db_session_factory = None

        # 加载 manifest（若未提供则从文件读取）
        if manifest is None:
            manifest = self._default_manifest()

        # 从 config_schema 提取默认值作为 ConfigManager defaults
        config_schema = manifest.get("config_schema", {})
        config_defaults = {k: v.get("default") for k, v in config_schema.items()}

        super().__init__(app=app, config=config or config_defaults, manifest=manifest)

    # ── 公开属性 ──────────────────────────────────────────────────

    @property
    def state(self) -> PluginState:
        """当前插件状态"""
        return self._state_info.state

    @state.setter
    def state(self, value) -> None:
        """兼容新版 SDK：PluginBase.__init__ 会对 self.state 赋值。"""
        self._state_info.state = value

    @property
    def uptime(self) -> Optional[float]:
        """运行时长（秒）"""
        if self._started_at:
            return time.time() - self._started_at
        return None

    # ── PluginBase.setup() 钩子 ──────────────────────────────────

    def setup(self) -> None:
        """
        [v5.7修复] 实现 PluginBase.setup() 钩子

        替代原来的 on_enable() 方法，由 PluginBase.__init__() 自动调用。
        """
        try:
            self._setup_routes()
            self._load_ratio_config()
            self._state_info.to_active()
            self._started_at = time.time()
            logger.info("[%s] 插件已激活，版本 %s", self.name, self.version)
        except Exception as e:
            self._state_info.to_failed(code=500, message=str(e))
            logger.error("[%s] 插件激活失败: %s", self.name, e)

    # ── 向后兼容生命周期方法 ──────────────────────────────────────

    def on_install(self) -> None:
        """安装时调用（向后兼容）"""
        logger.info("[%s] 安装完成", self.name)

    def on_enable(self) -> None:
        """启用时调用（向后兼容）"""
        if self.state != PluginState.ACTIVE:
            self.setup()

    def on_disable(self) -> None:
        """禁用时调用"""
        logger.info("[%s] 禁用中...", self.name)
        try:
            self._cleanup()
            self._state_info.to_disabled(by="system", reason="manual disable")
            self._started_at = None
            logger.info("[%s] 已禁用", self.name)
        except Exception as e:
            logger.error("[%s] 禁用失败: %s", self.name, e)

    def on_uninstall(self) -> None:
        """卸载时调用"""
        logger.info("[%s] 卸载中...", self.name)
        try:
            self._cleanup()
            self._state_info.to_disabled(by="system", reason="uninstall")
            logger.info("[%s] 已卸载", self.name)
        except Exception as e:
            logger.error("[%s] 卸载失败: %s", self.name, e)

    # ── 配置管理 ──────────────────────────────────────────────────

    def set_config(self, config: Dict[str, Any]) -> None:
        """设置插件配置（向后兼容）"""
        if hasattr(self, 'config') and hasattr(self.config, 'update'):
            self.config.update(config)

    def set_db_session_factory(self, factory) -> None:
        """设置数据库会话工厂"""
        self._db_session_factory = factory

    # ── 内部方法 ──────────────────────────────────────────────────

    def _setup_routes(self) -> None:
        """注册 FastAPI 路由"""
        try:
            from .router import router as token_router
            from .router import set_db_session_factory
        except ImportError:
            from router import router as token_router
            from router import set_db_session_factory

        # 设置数据库会话工厂
        if self._db_session_factory:
            set_db_session_factory(self._db_session_factory)

        # 将路由挂载到插件 router（PluginBase 不创建 self.router，用 _router + include app）
        self._router = token_router
        if self.app is not None and hasattr(self.app, "include_router"):
            self.app.include_router(self._router)
        logger.info("[%s] 路由已注册", self.name)

    def _load_ratio_config(self) -> None:
        """加载倍率配置"""
        try:
            from .config_loader import get_ratio_loader
            loader = get_ratio_loader()
            logger.info("[%s] 倍率配置已加载: %d 个模型", self.name, loader.get_model_count())
        except Exception as e:
            logger.warning("[%s] 倍率配置加载失败: %s", self.name, e)

    def _cleanup(self) -> None:
        """清理资源"""
        logger.info("[%s] 资源已清理", self.name)

    def _default_manifest(self) -> Dict[str, Any]:
        """默认 manifest"""
        from pathlib import Path
        manifest_path = Path(__file__).parent / "manifest.yaml"
        if manifest_path.exists():
            import yaml
            with open(manifest_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {
            "name": self.name,
            "version": self.version,
            "description": "DDW AI Hub Token额度管理插件",
        }

    def __repr__(self) -> str:
        return f"<TokenManagerPlugin name={self.name} state={self.state}>"


# ── 模块级入口函数 ──────────────────────────────────────────────


def register(app: FastAPI, config: Optional[Dict[str, Any]] = None) -> TokenManagerPlugin:
    """
    插件入口函数 — 由 PluginManager 调用

    Args:
        app: FastAPI 应用实例
        config: 插件配置字典

    Returns:
        TokenManagerPlugin 实例
    """
    plugin = TokenManagerPlugin(app=app, config=config)
    plugin.register()  # PluginBase.register() 挂载路由
    return plugin


# 向后兼容：保留 create_plugin 工厂函数
def create_plugin(config: Optional[Dict[str, Any]] = None) -> TokenManagerPlugin:
    """
    创建 TokenManagerPlugin 实例（向后兼容）

    注意: 独立运行时无需 app 参数；接入 DDW 平台时应使用 register(app)。
    """
    plugin = TokenManagerPlugin(config=config)
    return plugin
