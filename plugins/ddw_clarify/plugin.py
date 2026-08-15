"""DDW 对话反问澄清层 — Plugin entry point."""
from __future__ import annotations

import logging
from typing import Any

from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """对话反问澄清层：当用户提问模糊时自动反问，确认口径后再回答。"""

    name = "ddw-clarify"
    version = "1.0.0"
    router_prefix = "/api/v1/plugins/ddw-clarify"

    def __init__(
        self,
        app: Any = None,
        config: dict[str, Any] | None = None,
        manifest: dict[str, Any] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(app=app, config=config, manifest=manifest)

    def setup(self) -> None:
        from .router import router, set_service
        from .service import ClarifyService

        max_rounds = (self.config or {}).get("max_rounds", 3)
        service = ClarifyService(max_rounds=max_rounds)
        set_service(service)

        self._router = router
        self.app.include_router(router)
        logger.info("ddw-clarify v%s registered", self.version)


__all__ = ["Plugin"]
