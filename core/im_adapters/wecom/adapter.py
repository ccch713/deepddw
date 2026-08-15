"""WeCom (企业微信) adapter — production-grade.

Handles:
- Text + Markdown message sending (via WeCom API)
- Markdown card sending
- @mention-only group message policy (platform enforced)
- Identity mapping (WeCom user → DDW user)
- Retry with exponential backoff
- Structured logging + audit
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

from core.im_adapters.base import BaseIMAdapter, retry_with_backoff, write_audit

logger = logging.getLogger(__name__)

# WeCom API base
_API_BASE = "https://qyapi.weixin.qq.com/cgi-bin"


class WeComAdapter(BaseIMAdapter):
    name = "wecom"

    def __init__(
        self,
        *,
        credentials: Optional[Dict[str, str]] = None,
        require_mention: bool = True,
    ) -> None:
        super().__init__(credentials=credentials, require_mention=require_mention)
        self.corp_id = self.credentials.get("corp_id", os.getenv("DDW_WECOM_CORP_ID", ""))
        self.corp_secret = self.credentials.get("corp_secret", os.getenv("DDW_WECOM_CORP_SECRET", ""))
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------ #
    # Token management
    # ------------------------------------------------------------------ #

    async def _get_access_token(self) -> str:
        """Get or refresh the WeCom access_token."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token  # type: ignore[return-value]

        import httpx

        async def _fetch() -> str:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{_API_BASE}/gettoken",
                    params={"corpid": self.corp_id, "corpsecret": self.corp_secret},
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("errcode", 0) != 0:
                    raise RuntimeError(f"WeCom gettoken error: {data}")
                self._access_token = data["access_token"]
                self._token_expires_at = time.time() + data.get("expires_in", 7200)
                return self._access_token  # type: ignore[return-value]

        return await retry_with_backoff(_fetch)

    # ------------------------------------------------------------------ #
    # Sending
    # ------------------------------------------------------------------ #

    async def send_message(self, chat_id: str, content: str) -> str:
        t0 = time.monotonic()
        if not self.corp_id:
            logger.info("[mock wecom] send_message to=%s text=%s", chat_id, content[:120])
            await write_audit("wecom", "outbound", chat_id, "", content)
            return "mock-msg-id"

        async def _do_send() -> str:
            import httpx

            token = await self._get_access_token()
            body = {
                "chatid": chat_id,
                "msgtype": "text",
                "text": {"content": content},
                "safe": 0,
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{_API_BASE}/appchat/send",
                    params={"access_token": token},
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("errcode", 0) != 0:
                    raise RuntimeError(f"WeCom send error: {data}")
                return data.get("msgid", "")

        try:
            msg_id = await retry_with_backoff(_do_send)
        except Exception as exc:
            logger.error("wecom send_message failed: %s", exc)
            msg_id = ""

        elapsed = time.monotonic() - t0
        logger.info(
            "wecom outbound chat_id=%s len=%d elapsed=%.3fs",
            chat_id,
            len(content),
            elapsed,
        )
        await write_audit("wecom", "outbound", chat_id, "", content)
        return msg_id

    async def send_card(self, chat_id: str, card_data: Dict[str, Any]) -> str:
        t0 = time.monotonic()
        if not self.corp_id:
            logger.info("[mock wecom] send_card to=%s", chat_id)
            return "mock-card-id"

        async def _do_send() -> str:
            import httpx

            token = await self._get_access_token()
            # WeCom markdown message (closest to card)
            md_content = f"## {card_data.get('title', '')}\n{card_data.get('content', '')}"
            if card_data.get("button_text") and card_data.get("button_url"):
                md_content += f"\n[{card_data['button_text']}]({card_data['button_url']})"

            body = {
                "chatid": chat_id,
                "msgtype": "markdown",
                "markdown": {"content": md_content},
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{_API_BASE}/appchat/send",
                    params={"access_token": token},
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("errcode", 0) != 0:
                    raise RuntimeError(f"WeCom send_card error: {data}")
                return data.get("msgid", "")

        try:
            msg_id = await retry_with_backoff(_do_send)
        except Exception as exc:
            logger.error("wecom send_card failed: %s", exc)
            msg_id = ""

        elapsed = time.monotonic() - t0
        logger.info("wecom outbound card chat_id=%s elapsed=%.3fs", chat_id, elapsed)
        return msg_id

    # ------------------------------------------------------------------ #
    # Receiving
    # ------------------------------------------------------------------ #

    async def handle_incoming(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Translate a WeCom callback into a normalised dict.

        WeCom group bots only receive @messages (platform enforced).

        Expected input shape (WeCom message callback):

        .. code-block:: json

            {
              "FromUserName": "userid",
              "ToUserName": "corpid",
              "MsgType": "text",
              "Content": "hello",
              "MsgId": "xxx",
              "ChatId": "群聊id",
              "GetChatId": "群聊id"
            }
        """
        t0 = time.monotonic()

        user_id = message.get("FromUserName") or message.get("user_id", "")
        chat_id = (
            message.get("ChatId")
            or message.get("GetChatId")
            or message.get("chat_id", "")
        )
        msg_type = message.get("MsgType", "text")

        # Extract text content based on message type
        if msg_type == "text":
            text = message.get("Content") or message.get("content", "")
        elif msg_type == "markdown":
            text = message.get("Content") or message.get("content", "")
        else:
            text = self.normalise_text(message)

        # WeCom group detection: presence of ChatId indicates group message
        is_group = bool(chat_id)

        # WeCom bots only receive @mentions in groups (platform enforced)
        # but we check for @mention in content as safety
        if is_group:
            # WeCom marks @mentions in the content or via external attr
            is_at = message.get("isAt", False) or f"@{self.corp_id}" in text
            if not is_at:
                logger.debug("wecom ignoring non-@ group message chat_id=%s", chat_id)
                return None

        result: Dict[str, Any] = {
            "type": "text",
            "content": text,
            "user_id": user_id,
            "chat_id": chat_id,
            "is_group": is_group,
        }

        elapsed = time.monotonic() - t0
        logger.info(
            "wecom inbound chat_id=%s user_id=%s is_group=%s elapsed=%.3fs",
            chat_id,
            user_id,
            is_group,
            elapsed,
        )
        await write_audit("wecom", "inbound", chat_id, user_id, text)
        return result

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        if not self.corp_id:
            return {"user_id": user_id, "name": "mock-wecom-user", "phone": ""}

        async def _do_fetch() -> Dict[str, Any]:
            import httpx

            token = await self._get_access_token()
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{_API_BASE}/user/get",
                    params={"access_token": token, "userid": user_id},
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("errcode", 0) != 0:
                    raise RuntimeError(f"WeCom get_user error: {data}")
                return {
                    "user_id": user_id,
                    "name": data.get("name", ""),
                    "phone": data.get("mobile", ""),
                    "department": data.get("department", []),
                    "position": data.get("position", ""),
                }

        try:
            return await retry_with_backoff(_do_fetch)
        except Exception as exc:
            logger.error("wecom get_user_info failed: %s", exc)
            return {"user_id": user_id, "name": "", "phone": ""}
