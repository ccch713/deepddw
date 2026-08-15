"""DDW 企业知识库引擎 — Plugin entry point."""

from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """企业知识库引擎：上传文档→解析→分块→embedding→检索→LLM 问答。"""

    name = "ddw_ent_knowledge"
    version = "1.0.0"

    def setup(self) -> None:
        """Register FastAPI router on the host app."""
        from .router import router
        self._router = router
        if self.app is not None:
            self.app.include_router(router)
        logger.info("ddw_ent_knowledge v1.0.0 registered")


__all__ = ["Plugin"]
