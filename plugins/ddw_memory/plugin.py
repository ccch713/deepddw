"""ddw_memory 插件 Plugin 类 — 四层持久化记忆引擎。"""
from __future__ import annotations

import logging

from sdk.plugin_base import PluginBase

from . import PLUGIN_NAME, VERSION
from .router import build_router

logger = logging.getLogger(__name__)


class Plugin(PluginBase):
    """企业记忆引擎插件主类。"""

    name = PLUGIN_NAME
    version = VERSION

    def __init__(self, app=None, config=None, manifest=None, **kwargs):
        super().__init__(app=app, config=config, manifest=manifest)

    def setup(self) -> None:
        router = build_router()
        self._router = router
        if self.app:
            self.app.include_router(router)

        # ── 事件总线订阅：对话轮次完成 → 自动捕获记忆 ──
        try:
            from core.events.bus import get_bus
            bus = get_bus()
            bus.subscribe("conversation.turn.completed", self._on_turn_completed)
            logger.info("ddw-memory: subscribed to conversation.turn.completed")
        except Exception as e:
            logger.warning("ddw-memory: event bus subscribe failed (non-fatal): %s", e)

        logger.info("ddw-memory plugin %s initialized (SQLAlchemy engine)", VERSION)

    @staticmethod
    async def _on_turn_completed(payload: dict) -> None:
        """事件回调：对话轮次完成后，检查是否触发自动捕获。

        payload 期望字段:
            source: str          # 事件来源（ddw_online_cs 等）
            tenant_id: int
            user_id: int
            session_id: str
            messages: list[dict]  # 完整对话历史
        """
        try:
            # 客服对话（ddw_online_cs）默认不捕获：
            # 客户咨询会污染员工级记忆（员工记忆=员工工作知识语义）
            source = payload.get("source", "")
            if source == "ddw_online_cs":
                logger.debug("skip auto-capture: source=%s (customer service)", source)
                return

            from .auto_capture import maybe_capture_session
            from .service import MemoryService

            tenant_id = payload.get("tenant_id", 1)
            user_id = payload.get("user_id", 0)
            session_id = payload.get("session_id", "")
            messages = payload.get("messages", [])

            if not messages or not session_id:
                return

            svc = MemoryService()
            config = await svc.get_capture_config(tenant_id)
            if not config.get("enabled", True):
                return

            async def _llm_chat(system: str, user: str) -> str:
                from core.llm_gateway.base import ChatMessage
                from core.llm_gateway.gateway import chat as gateway_chat
                resp = await gateway_chat([
                    ChatMessage(role="system", content=system),
                    ChatMessage(role="user", content=user),
                ])
                return resp.content

            result = await maybe_capture_session(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                messages=messages,
                config=config,
                llm_chat_fn=_llm_chat,
                create_pending_fn=svc.create_pending_capture,
            )
            if result:
                logger.info("ddw-memory: auto-captured session %s (confidence=%.2f)",
                            session_id, result.get("confidence", 0))
        except Exception as e:
            logger.warning("ddw-memory: _on_turn_completed error: %s", e)


__all__ = ["Plugin"]
