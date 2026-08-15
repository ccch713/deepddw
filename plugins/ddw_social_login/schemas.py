"""Pydantic 请求/响应模型 —— 必须在模块顶层定义，禁止在函数/闭包内定义。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ChannelConfig(BaseModel):
    """单个通道的配置"""

    provider: str = Field(..., description="通道标识: wechat_open / qq / dingtalk / feishu")
    enabled: bool = Field(False, description="是否启用")
    appid: Optional[str] = Field(None, description="第三方应用 AppID")
    app_secret: Optional[str] = Field(None, description="第三方应用 AppSecret")
    callback_url: Optional[str] = Field(None, description="回调 URL（可选，不填则自动生成）")


class ChannelConfigSave(BaseModel):
    """管理员保存通道配置"""

    channels: List[ChannelConfig]


class ChannelStatus(BaseModel):
    """通道状态（前端渲染按钮用）"""

    provider: str
    display_name: str  # "微信扫码" / "QQ 登录" / "钉钉登录" / "飞书登录"
    enabled: bool


class SocialBindRequest(BaseModel):
    """已登录用户绑定第三方账号"""

    provider: str
    code: str
    state: str


class SocialLoginCallbackResp(BaseModel):
    """扫码登录成功响应"""

    access_token: str
    token_type: str = "bearer"
    user: dict
    tenant: dict


class ErrorResponse(BaseModel):
    """统一错误响应"""

    code: str
    message: str


class BindingInfo(BaseModel):
    """用户绑定信息"""

    provider: str
    provider_name: Optional[str] = None
    bound_at: Optional[datetime] = None
