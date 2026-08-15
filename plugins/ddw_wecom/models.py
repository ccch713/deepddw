"""DDW 企业微信插件 Pydantic 数据模型。"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class WeComUser(BaseModel):
    """企业微信用户 ↔ DDW 用户映射。"""

    wecom_userid: str = Field(..., description="企微 UserID")
    ddw_user_id: str = Field(..., description="DDW 平台用户 ID")
    corp_id: str = Field(..., description="企业 ID")
    department_ids: list[int] = Field(default_factory=list, description="企微部门 ID 列表")
    avatar_url: Optional[str] = Field(None, description="头像 URL")
    external_identity: dict[str, str] = Field(
        default_factory=dict,
        description="第三方身份绑定 {provider: external_id}",
    )
    name: Optional[str] = Field(None, description="用户姓名")
    mobile: Optional[str] = Field(None, description="手机号")
    email: Optional[str] = Field(None, description="邮箱")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class WeComDepartment(BaseModel):
    """企微部门 ↔ DDW 部门映射。"""

    wecom_dept_id: int = Field(..., description="企微部门 ID")
    name: str = Field(..., description="部门名称")
    parent_id: Optional[int] = Field(None, description="企微上级部门 ID")
    ddw_department_id: Optional[str] = Field(None, description="映射到 DDW 的部门 ID")


class OAuthCallback(BaseModel):
    """OAuth 回调参数 + 解析后的用户信息。"""

    code: str = Field(..., description="企微 OAuth 授权码")
    state: str = Field(default="", description="防 CSRF 状态码")
    user_info: Optional[dict] = Field(None, description="企微返回的用户信息")


class MessageType(str, Enum):
    TEXT = "text"
    MARKDOWN = "markdown"
    IMAGE = "image"
    NEWS = "news"


class MessageStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class MessageTemplate(BaseModel):
    """消息模板（占位，后续对接推送）。"""

    template_id: str = Field(..., description="模板 ID")
    content: str = Field(..., description="模板内容")
    msg_type: MessageType = Field(MessageType.TEXT, description="消息类型")
    status: MessageStatus = Field(MessageStatus.PENDING, description="发送状态")
    created_at: datetime = Field(default_factory=datetime.utcnow)


__all__ = [
    "MessageStatus",
    "MessageTemplate",
    "MessageType",
    "OAuthCallback",
    "WeComDepartment",
    "WeComUser",
]
