"""DDW 官网插件 — 官网配置管理（主题模版/站点信息/页面清单）.

官网作为 DDW 底座的一个插件能力：
- 主题模版（standard/holiday/mourning）由 DDW 底座管理后台统一切换
- 前台页面通过 GET /api/v1/plugins/ddw-website/theme 读取当前主题
- 站点基础信息（公司全称/备案/联系方式）统一管理，页面不硬编码
"""
from __future__ import annotations

import logging
from typing import Any, Dict  # noqa: F401  (re-export for compatibility)

logger = logging.getLogger(__name__)

PLUGIN_NAME = "ddw-website"
VERSION = "1.0.0"


class Plugin:
    """官网插件 — 主题与站点配置管理."""

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = "/api/v1/plugins/ddw-website"

    def setup(self) -> None:
        """Register FastAPI router on the host app."""
        from .router import router
        self._router = router
        self.app.include_router(router)
        logger.info("ddw-website v%s registered", VERSION)


__all__ = ["Plugin"]
