"""Feishu (Lark) adapter — production-grade.

Handles:
- Text + Markdown message sending (via Feishu OpenAPI)
- Interactive card sending
- Configurable group message policy (require_mention flag)
- Rate limiting (10 msgs/min per group when require_mention=False)
- Identity mapping (Feishu user → DDW user)
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

# Feishu OpenAPI base
_OPENAPI_BASE = "https://open.feishu.cn/open-apis"


class FeishuAdapter(BaseIMAdapter):
    name = "feishu"

    def __init__(
        self,
        *,
        credentials: Optional[Dict[str, str]] = None,
        require_mention: bool = True,
    ) -> None:
        super().__init__(credentials=credentials, require_mention=require_mention)
        self.app_id = self.credentials.get("app_id", os.getenv("DDW_FEISHU_APP_ID", ""))
        self.app_secret = self.credentials.get("app_secret", os.getenv("DDW_FEISHU_APP_SECRET", ""))
        self._tenant_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------ #
    # Token management
    # ------------------------------------------------------------------ #

    async def _get_tenant_token(self) -> str:
        """Get or refresh the Feishu tenant_access_token."""
        if self._tenant_token and time.time() < self._token_expires_at - 60:
            return self._tenant_token  # type: ignore[return-value]

        import httpx

        async def _fetch() -> str:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{_OPENAPI_BASE}/auth/v3/tenant_access_token/internal",
                    json={"app_id": self.app_id, "app_secret": self.app_secret},
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("code", 0) != 0:
                    raise RuntimeError(f"Feishu token error: {data}")
                self._tenant_token = data["tenant_access_token"]
                self._token_expires_at = time.time() + data.get("expire", 7200)
                return self._tenant_token  # type: ignore[return-value]

        return await retry_with_backoff(_fetch)

    # ------------------------------------------------------------------ #
    # Sending
    # ------------------------------------------------------------------ #

    async def send_message(self, chat_id: str, content: str) -> str:
        t0 = time.monotonic()
        if not self.app_id:
            logger.info("[mock feishu] send_message to=%s text=%s", chat_id, content[:120])
            await write_audit("feishu", "outbound", chat_id, "", content)
            return "mock-msg-id"

        async def _do_send() -> str:
            import httpx
            import json as json_mod

            token = await self._get_tenant_token()
            # Feishu uses msg_type: "text" or "post" (rich text / markdown)
            body = {
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json_mod.dumps({"text": content}),
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{_OPENAPI_BASE}/im/v1/messages",
                    params={"receive_id_type": "chat_id"},
                    headers={"Authorization": f"Bearer {token}"},
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("code", 0) != 0:
                    raise RuntimeError(f"Feishu send error: {data}")
                return data.get("data", {}).get("message_id", "")

        try:
            msg_id = await retry_with_backoff(_do_send)
        except Exception as exc:
            logger.error("feishu send_message failed: %s", exc)
            msg_id = ""

        elapsed = time.monotonic() - t0
        logger.info(
            "feishu outbound chat_id=%s len=%d elapsed=%.3fs",
            chat_id,
            len(content),
            elapsed,
        )
        await write_audit("feishu", "outbound", chat_id, "", content)
        return msg_id

    async def send_card(self, chat_id: str, card_data: Dict[str, Any]) -> str:
        t0 = time.monotonic()
        if not self.app_id:
            logger.info("[mock feishu] send_card to=%s", chat_id)
            return "mock-card-id"

        async def _do_send() -> str:
            import httpx
            import json as json_mod

            token = await self._get_tenant_token()
            # Build Feishu interactive card
            card = {
                "header": {
                    "title": {"tag": "plain_text", "content": card_data.get("title", "")},
                },
                "elements": [
                    {"tag": "markdown", "content": card_data.get("content", "")},
                ],
            }
            if card_data.get("button_text") and card_data.get("button_url"):
                card["elements"].append({
                    "tag": "action",
                    "actions": [{
                        "tag": "button",
                        "text": {"tag": "plain_text", "content": card_data["button_text"]},
                        "url": card_data["button_url"],
                        "type": "primary",
                    }],
                })

            body = {
                "receive_id": chat_id,
                "msg_type": "interactive",
                "content": json_mod.dumps(card),
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{_OPENAPI_BASE}/im/v1/messages",
                    params={"receive_id_type": "chat_id"},
                    headers={"Authorization": f"Bearer {token}"},
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("code", 0) != 0:
                    raise RuntimeError(f"Feishu send_card error: {data}")
                return data.get("data", {}).get("message_id", "")

        try:
            msg_id = await retry_with_backoff(_do_send)
        except Exception as exc:
            logger.error("feishu send_card failed: %s", exc)
            msg_id = ""

        elapsed = time.monotonic() - t0
        logger.info("feishu outbound card chat_id=%s elapsed=%.3fs", chat_id, elapsed)
        return msg_id

    # ------------------------------------------------------------------ #
    # Receiving
    # ------------------------------------------------------------------ #

    async def handle_incoming(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Translate a Feishu event callback into a normalised dict.

        Expected input shape (Feishu im.message.receive_v1 event body):

        .. code-block:: json

            {
              "sender": {"sender_id": {"user_id": "ou_xxx"}, "sender_type": "user"},
              "message": {
                "chat_id": "oc_xxx",
                "chat_type": "group",
                "message_type": "text",
                "content": "{\"text\": \"hello\"}",
                "mentions": [{"id": {"user_id": "ou_bot"}}]
              }
            }
        """
        import json as json_mod

        t0 = time.monotonic()

        sender = message.get("sender", {})
        msg_obj = message.get("message", {})

        user_id = sender.get("sender_id", {}).get("user_id", "")
        chat_id = msg_obj.get("chat_id", "")
        chat_type = msg_obj.get("chat_type", "p2p")
        is_group = chat_type == "group"

        # Parse content (JSON string)
        raw_content = msg_obj.get("content", "{}")
        try:
            content_obj = json_mod.loads(raw_content) if isinstance(raw_content, str) else raw_content
        except (json_mod.JSONDecodeError, TypeError):
            content_obj = {}

        text = content_obj.get("text", "")

        # Check @mention
        has_mention = bool(msg_obj.get("mentions"))

        # Group message policy
        if is_group:
            if self.require_mention and not has_mention:
                logger.debug("feishu ignoring non-@ group message chat_id=%s", chat_id)
                return None

            # Rate limiting when require_mention=False (respond to all group msgs)
            if not self.require_mention:
                if not self._check_rate_limit(chat_id):
                    logger.warning(
                        "feishu rate-limited group chat_id=%s (>10 msgs/60s)",
                        chat_id,
                    )
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
            "feishu inbound chat_id=%s user_id=%s is_group=%s elapsed=%.3fs",
            chat_id,
            user_id,
            is_group,
            elapsed,
        )
        await write_audit("feishu", "inbound", chat_id, user_id, text)
        return result

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        if not self.app_id:
            return {"user_id": user_id, "name": "mock-feishu-user", "phone": ""}

        async def _do_fetch() -> Dict[str, Any]:
            import httpx

            token = await self._get_tenant_token()
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{_OPENAPI_BASE}/contact/v3/users/{user_id}",
                    params={"user_id_type": "open_id"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("code", 0) != 0:
                    raise RuntimeError(f"Feishu get_user error: {data}")
                user = data.get("data", {}).get("user", {})
                return {
                    "user_id": user_id,
                    "name": user.get("name", ""),
                    "phone": user.get("mobile", ""),
                    "department_ids": user.get("department_ids", []),
                    "title": user.get("job_title", ""),
                }

        try:
            return await retry_with_backoff(_do_fetch)
        except Exception as exc:
            logger.error("feishu get_user_info failed: %s", exc)
            return {"user_id": user_id, "name": "", "phone": ""}
