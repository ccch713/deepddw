"""DDW 设计人员资质管理插件 Plugin 类。

复用平台 ``sdk.plugin_base.PluginBase``，挂载 router，提供 14 个 API。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter

from plugins.ddw_personnel_qual import PLUGIN_NAME, VERSION

# 触发 models 注册到 Base.metadata（确保 init_db() 能建表）
from plugins.ddw_personnel_qual import models as _models  # noqa: F401
from plugins.ddw_personnel_qual.services import (
    CertService,
    ExpiryService,
    RenewalService,
)
from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        warn_days = int(self.config.get("expiry_warn_days", 90))
        self.cert_service = CertService()
        self.expiry_service = ExpiryService(warn_days=warn_days)
        self.renewal_service = RenewalService()

        # 注册 router
        from plugins.ddw_personnel_qual.router import build_router

        self._router: APIRouter = build_router(self)
        self.app.include_router(self._router)
        logger.info("ddw-personnel-qual plugin %s initialized (warn_days=%d)", VERSION, warn_days)

    # -------- 健康检查用业务方法 -------- #

    def get_services(self) -> Dict[str, Any]:
        return {
            "cert": self.cert_service,
            "expiry": self.expiry_service,
            "renewal": self.renewal_service,
        }


__all__ = ["Plugin"]
