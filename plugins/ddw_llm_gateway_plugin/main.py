"""
DDW LLM Gateway 插件 — LLM 统一网关入口

继承 SDK PluginBase，使用 SDK PluginState 状态机。
提供 51 种渠道类型支持、负载均衡、断路器、流式 SSE 转发。

状态机（使用 SDK PluginState）:
  LOADING → ACTIVE → FAILED / DISABLED / NEEDS_UPDATE
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI

# [v5.7] 导入 SDK 标准基类
from sdk.plugin_base import PluginBase
from sdk.plugin_state import PluginState, PluginStateInfo

logger = logging.getLogger(__name__)


class LLMGatewayPlugin(PluginBase):
    """
    DDW LLM Gateway 插件

    继承 SDK PluginBase，使用 SDK PluginState 状态机。
    提供 OpenAI 兼容格式的 LLM 请求转发、渠道管理、负载均衡。

    核心职责:
    1. 统一 LLM 请求入口（OpenAI 兼容格式）
    2. 51 种渠道类型 YAML 配置化
    3. 优先级+随机+权重负载均衡
    4. 失败重试 + 渠道自动禁用/启用
    5. 流式 SSE 透传
    6. 与 ddw-token-manager 预消费/后消费集成
    """

    name = "ddw-llm-gateway"
    version = "1.0.0"
    router_prefix = "/api/llm-gateway"

    def __init__(
        self,
        app: FastAPI = None,
        config: Optional[Dict[str, Any]] = None,
        manifest: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        self._state_info = PluginStateInfo(
            state=PluginState.LOADING,
            name=self.name,
            version=self.version,
        )
        super().__init__(app=app, config=config, manifest=manifest)
        for key, value in kwargs.items():
            setattr(self, key, value)

    def setup(self) -> None:
        """
        实现 PluginBase.setup() 钩子

        由 PluginBase.__init__() 自动调用。
        初始化路由、渠道管理器、负载均衡器、断路器、健康监控。
        """
        try:
            self._setup_routes()
            self._init_components()
            self._state_info.to_active()
            logger.info("[%s] 插件已激活，版本 %s", self.name, self.version)
        except Exception as e:
            self._state_info.to_failed(code=500, message=str(e))
            logger.error("[%s] 插件激活失败: %s", self.name, e)

    def _setup_routes(self) -> None:
        """注册 FastAPI 路由"""
        try:
            from .router import router as gateway_router
        except ImportError:
            from router import router as gateway_router
        self._router = gateway_router
        if self.app is not None and hasattr(self.app, "include_router"):
            self.app.include_router(self._router)

    def _init_components(self) -> None:
        """初始化网关核心组件"""
        from .channel_manager import ChannelManager
        from .circuit_breaker import CircuitBreaker
        from .load_balancer import LoadBalancer

        self._channel_manager = ChannelManager()
        self._circuit_breaker = CircuitBreaker()
        self._load_balancer = LoadBalancer(
            success_rate_threshold=self.config.get(
                "channel_disable_threshold", 0.5
            )
        )
        logger.info("[%s] 核心组件初始化完成", self.name)


def register(app: FastAPI, **kwargs: Any) -> None:
    """插件入口函数 — 由 PluginManager 调用"""
    plugin = LLMGatewayPlugin(app=app, **kwargs)
    plugin.register()
