"""DDW AI 组织插件 Plugin 类。"""
from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from . import models as _models  # noqa: F401  触发模型注册到 Base.metadata
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """AI 组织插件主类。"""

    name = PLUGIN_NAME
    version = VERSION

    def setup(self) -> None:
        """注册路由。"""
        self._router = build_router()
        self.app.include_router(self._router)
        logger.info("ddw-org plugin %s initialized", VERSION)


async def seed_for_tenant(tenant_id: int) -> dict:
    """为指定租户创建种子数据（公共 API，供上层调用）。"""
    from core.database.session import session_scope
    from core.database.tenant_filter import bypass_tenant_filter
    from .services.seed import seed_org_for_tenant

    async with session_scope() as db, bypass_tenant_filter():
        return await seed_org_for_tenant(db, tenant_id)


__all__ = ["Plugin", "seed_for_tenant"]
