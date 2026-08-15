"""DDW 产品文档栏目插件 Plugin 类。

setup() 中：
1. import models 触发建表注册（init_db create_all 自动建 docs_* 三张表）
2. 挂载 FastAPI router
3. 注册 LLM 工具 ddw.docs_portal.search（决策 3，供网关/Agent 调用）
"""
from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from . import models as _models  # noqa: F401  触发模型注册到 Base.metadata
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """产品文档栏目插件主类。"""

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        """注册路由 + MCP 工具。

        注意：router 不在此处 include_router——PluginBase.register() 会
        在 setup() 之后统一挂载 self._router（避免路由重复注册）。
        """
        self._router = build_router()

        # 决策 3：注册 docs_search 工具（失败不阻塞插件加载）
        try:
            from core.mcp.server import get_mcp_server

            from .llm_tool import register_docs_tool

            server = get_mcp_server()
            if server is not None:
                register_docs_tool(server.tools)
        except Exception as exc:  # noqa: BLE001
            logger.warning("docs_portal: MCP tool registration skipped: %s", exc)

        logger.info("ddw-docs-portal plugin %s initialized", VERSION)


__all__ = ["Plugin"]
