"""WeChat Service Account adapter"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from core.im_adapters.base import BaseIMAdapter

logger = logging.getLogger(__name__)

class WeChatAdapter(BaseIMAdapter):
    name = "wechat"
    def __init__(self, *, credentials: Optional[Dict[str, str]] = None) -> None:
        super().__init__(credentials=credentials)
        self.app_id = self.credentials.get("app_id", os.getenv("DDW_WECHAT_APP_ID", ""))
        self.app_secret = self.credentials.get("app_secret", os.getenv("DDW_WECHAT_APP_SECRET", ""))

    async def send_message(self, chat_id: str, content: str) -> str:
        if not self.app_id:
            logger.info("[mock wechat] send to=%s text=%s", chat_id, content[:120])
        return "mock-msg-id"

    async def send_template_message(self, chat_id: str, template_id: str, data: Dict[str, Any]) -> str:
        logger.info("[mock wechat] template to=%s tpl=%s", chat_id, template_id)
        return "mock-template-id"

    async def handle_incoming(self, message: Dict[str, Any]) -> Dict[str, Any]:
        return {"user_id": message.get("user_id", ""), "text": self.normalise_text(message)}

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        return {"user_id": user_id, "name": "", "openid": ""}
