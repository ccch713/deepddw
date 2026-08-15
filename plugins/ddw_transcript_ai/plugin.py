from __future__ import annotations

"""DDW 转写与结构化插件 Plugin 类（DDW AI Hub — 销售端 CRM P3-3）。"""

import logging

from plugins.embedded_llm.engine import EmbeddedLLM

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from .router import build_router
from .services import TranscriptService

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """转写与结构化插件主类。

    - 在 ``setup()`` 中**只创建一次** :class:`EmbeddedLLM`（echo backend）
    - 通过 ``TranscriptService`` 暴露 4 个 AI 能力
    - 真实生产环境只需切换 EmbeddedLLM backend（llama.cpp / 外部 API），
      业务层无需改动
    """

    name = PLUGIN_NAME
    version = VERSION
    router_prefix = f"/api/v1/plugins/{PLUGIN_NAME}"

    def setup(self) -> None:
        """初始化 LLM + 服务 + 路由。"""
        # 1) 构造 LLM（默认 echo backend，无外部 API key 依赖）
        self.llm = EmbeddedLLM(knowledge_dir=None)

        # 2) 业务服务
        self.service = TranscriptService(self.llm)

        # 3) 路由
        self._router = build_router(self.service)
        self.app.include_router(self._router)

        logger.info(
            "ddw-transcript-ai plugin %s initialized (backend=%s)",
            VERSION,
            self.service._backend_name(),
        )


__all__ = ["Plugin"]
