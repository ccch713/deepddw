"""DDW AI Hub 插件市场模块 — Phase 3 核心功能。

提供插件注册表、安装/卸载、市场 API 等完整市场能力。
"""

from core.marketplace.router import router as marketplace_router

__all__ = ["marketplace_router"]
