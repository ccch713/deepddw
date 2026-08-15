"""DDW 企业微信插件核心业务逻辑。

内存存储，覆盖 OAuth 回调 + JIT 建号 + 部门同步 + 消息通道占位。
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from .models import (
    MessageStatus,
    MessageTemplate,
    MessageType,
    OAuthCallback,
    WeComDepartment,
    WeComUser,
)

logger = logging.getLogger(__name__)


class WeComService:
    """企业微信 OAuth + JIT 建号 + 部门同步服务。"""

    def __init__(
        self,
        corp_id: str = "test_corp_id",
        agent_id: str = "test_agent_id",
        corp_secret: str = None,
        redirect_uri: str = "https://example.com/wecom/oauth/callback",
    ) -> None:
        self.corp_id = corp_id
        self.agent_id = agent_id
        if corp_secret is None:
            import logging; logging.getLogger(__name__).warning("ddw_wecom: corp_secret not configured — WeCom integration disabled")
        self.corp_secret = corp_secret
        self.redirect_uri = redirect_uri

        self._users: dict[str, WeComUser] = {}
        self._departments: dict[int, WeComDepartment] = {}
        self._messages: list[MessageTemplate] = []

    # ========== OAuth ==========

    def get_authorize_url(self, state: str = "") -> str:
        """生成企微 OAuth 授权跳转 URL。"""
        return (
            f"https://open.work.weixin.qq.com/wwopen/sso/qrConnect"
            f"?appid={self.corp_id}"
            f"&agentid={self.agent_id}"
            f"&redirect_uri={self.redirect_uri}"
            f"&state={state}"
        )

    def handle_oauth_callback(self, callback: OAuthCallback) -> WeComUser:
        """处理 OAuth 回调：code → access_token → 用户信息 → JIT 建号/登录。

        实际场景中需要调企微 API，这里用模拟逻辑以便测试。
        """
        # 模拟 code → access_token
        access_token = self._exchange_code(callback.code)
        if not access_token:
            raise ValueError("invalid oauth code")

        # 模拟 access_token → 用户信息
        user_info = callback.user_info or self._get_user_info(access_token)
        wecom_userid = user_info.get("userid", "")
        if not wecom_userid:
            raise ValueError("userid not found in user info")

        # JIT: 已存在则登录，不存在则建号
        existing = self._users.get(wecom_userid)
        if existing:
            logger.info("wecom user %s logged in (existing)", wecom_userid)
            return existing

        ddw_user_id = f"ddw_{uuid.uuid4().hex[:8]}"
        user = WeComUser(
            wecom_userid=wecom_userid,
            ddw_user_id=ddw_user_id,
            corp_id=self.corp_id,
            department_ids=user_info.get("department", []),
            avatar_url=user_info.get("avatar"),
            name=user_info.get("name"),
            mobile=user_info.get("mobile"),
            email=user_info.get("email"),
        )
        self._users[wecom_userid] = user
        logger.info("wecom user %s JIT-created as ddw user %s", wecom_userid, ddw_user_id)
        return user

    def _exchange_code(self, code: str) -> Optional[str]:
        """模拟 code → access_token 交换。"""
        if code.startswith("valid_"):
            return f"token_{code}"
        return None

    def _get_user_info(self, access_token: str) -> dict:
        """模拟 access_token → 用户信息。"""
        return {
            "userid": "mock_user",
            "name": "Mock User",
            "department": [1, 2],
            "avatar": "https://example.com/avatar.png",
            "mobile": "13800000000",
            "email": "mock@example.com",
        }

    # ========== 部门同步 ==========

    def sync_departments(self, departments: list[WeComDepartment]) -> list[WeComDepartment]:
        """同步企微部门到本地，并建立 DDW 部门映射。"""
        synced = []
        for dept in departments:
            ddw_dept_id = self._departments.get(dept.wecom_dept_id)
            if ddw_dept_id and ddw_dept_id.ddw_department_id:
                dept.ddw_department_id = ddw_dept_id.ddw_department_id
            else:
                dept.ddw_department_id = f"ddw_dept_{dept.wecom_dept_id}"
            self._departments[dept.wecom_dept_id] = dept
            synced.append(dept)
        logger.info("synced %d departments", len(synced))
        return synced

    def get_department(self, wecom_dept_id: int) -> Optional[WeComDepartment]:
        return self._departments.get(wecom_dept_id)

    def list_departments(self) -> list[WeComDepartment]:
        return list(self._departments.values())

    # ========== 用户 ==========

    def get_user(self, wecom_userid: str) -> Optional[WeComUser]:
        return self._users.get(wecom_userid)

    def list_users(self) -> list[WeComUser]:
        return list(self._users.values())

    # ========== External Identity ==========

    def bind_external_identity(
        self, wecom_userid: str, provider: str, external_id: str
    ) -> Optional[WeComUser]:
        """绑定第三方身份。"""
        user = self._users.get(wecom_userid)
        if not user:
            return None
        user.external_identity[provider] = external_id
        self._users[wecom_userid] = user
        logger.info("bound %s -> %s:%s", wecom_userid, provider, external_id)
        return user

    def get_user_by_external_identity(
        self, provider: str, external_id: str
    ) -> Optional[WeComUser]:
        """通过第三方身份反查用户。"""
        for user in self._users.values():
            if user.external_identity.get(provider) == external_id:
                return user
        return None

    # ========== 消息通道（占位） ==========

    def send_message(
        self,
        template_id: str,
        content: str,
        msg_type: MessageType = MessageType.TEXT,
    ) -> MessageTemplate:
        """发送消息（占位实现，仅记录模板，不实际推送）。"""
        msg = MessageTemplate(
            template_id=template_id,
            content=content,
            msg_type=msg_type,
            status=MessageStatus.PENDING,
        )
        self._messages.append(msg)
        logger.info("message queued (placeholder): %s", template_id)
        return msg

    def list_messages(self) -> list[MessageTemplate]:
        return list(self._messages)


__all__ = ["WeComService"]
