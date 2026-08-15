"""DDW LLM Gateway 插件"""
try:
    from .main import LLMGatewayPlugin, register
except Exception:
    # 当作为独立模块运行或 SDK 不可用时，延迟导入
    def register(app, **kwargs):  # type: ignore[misc]
        """插件入口函数 — 由 PluginManager 调用"""
        from main import LLMGatewayPlugin
        plugin = LLMGatewayPlugin(app=app, **kwargs)
        plugin.register()

    LLMGatewayPlugin = None  # type: ignore[assignment,misc]

__all__ = ["LLMGatewayPlugin", "register"]
