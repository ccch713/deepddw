"""org_relay Plugin 类（默认关闭：enabled=false 时不挂任何路由）。"""

from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from .config import get_org_relay_config

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """组织连接插件（bindcode-v1 服务端）。

    setup() 在启用时构建路由；未启用时 self._router 保持 None，
    PluginBase.register() 将跳过挂载——不产生任何运行时痕迹。
    """

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        cfg = get_org_relay_config()
        if not cfg["enabled"]:
            logger.info("org_relay disabled (org_relay.enabled=false); no routes mounted")
            return
        if not cfg["product_tokens"]:
            logger.warning(
                "org_relay enabled but product_tokens empty — "
                "public bind/unbind/me endpoints will reject all requests; "
                "set org_relay.product_tokens or DDW_ORG_RELAY_PRODUCT_TOKENS"
            )
        from .router import build_router

        self._router = build_router()
        logger.info("org_relay plugin %s registered (bindcode-v1)", VERSION)
