"""通道配置管理 —— 读写 manifest config 中的通道信息。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from senweaver_oauth import AuthConfig
from senweaver_oauth.source.dingtalk import AuthDingtalkSource
from senweaver_oauth.source.feishu import AuthFeishuSource
from senweaver_oauth.source.qq import AuthQqSource
from senweaver_oauth.source.wechat_open import AuthWechatOpenSource

from .schemas import ChannelConfig, ChannelStatus

# ---- 常量 ----

VALID_PROVIDERS = ("wechat_open", "qq", "dingtalk", "feishu")

PROVIDER_DISPLAY_NAMES: Dict[str, str] = {
    "wechat_open": "微信扫码",
    "qq": "QQ 登录",
    "dingtalk": "钉钉登录",
    "feishu": "飞书登录",
}

PROVIDER_MAP: Dict[str, Any] = {
    "wechat_open": AuthWechatOpenSource,
    "qq": AuthQqSource,
    "dingtalk": AuthDingtalkSource,
    "feishu": AuthFeishuSource,
}

PROVIDER_PHONE_PREFIX: Dict[str, str] = {
    "wechat_open": "wx",
    "qq": "qq",
    "dingtalk": "dt",
    "feishu": "fs",
}


class ConfigManager:
    """管理 social-login 插件的通道配置。

    配置存储在 plugin.config dict 中，通过 PluginBase 传入。
    结构示例::

        {
            "enabled_channels": ["dingtalk", "feishu"],
            "auto_register": True,
            "allowed_callback_domains": ["ddw.9cio.com"],
            "default_tenant_id": 1,
            "channels": {
                "dingtalk": {"enabled": True, "appid": "xxx", "app_secret": "yyy", "callback_url": None},
                "feishu":   {"enabled": True, "appid": "aaa", "app_secret": "bbb", "callback_url": None},
            }
        }
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._config: Dict[str, Any] = config if config is not None else {}

    # ---------- 读取 ----------

    @property
    def auto_register(self) -> bool:
        return bool(self._config.get("auto_register", True))

    @property
    def default_tenant_id(self) -> int:
        return int(self._config.get("default_tenant_id", 1))

    @property
    def default_role(self) -> str:
        return self._config.get("default_role", "member")

    @property
    def allowed_callback_domains(self) -> List[str]:
        return list(self._config.get("allowed_callback_domains", ["ddw.9cio.com"]))

    @property
    def enabled_channels(self) -> List[str]:
        """返回已启用通道列表（从 channels dict 中筛选 enabled=True）。"""
        channels = self._config.get("channels", {})
        return [p for p, cfg in channels.items() if cfg.get("enabled")]

    def get_channel_raw(self, provider: str) -> Optional[Dict[str, Any]]:
        """返回某通道的原始配置 dict。"""
        return self._config.get("channels", {}).get(provider)

    def get_channel_config(self, provider: str) -> Optional[AuthConfig]:
        """构建 senweaver-oauth AuthConfig；未配置或缺 appid/secret 返回 None。"""
        raw = self.get_channel_raw(provider)
        if not raw or not raw.get("appid") or not raw.get("app_secret"):
            return None
        return AuthConfig(
            client_id=raw["appid"],
            client_secret=raw["app_secret"],
            redirect_uri=raw.get("callback_url"),
        )

    def get_channel_list(self) -> List[ChannelConfig]:
        """返回全部 4 个通道的配置（供管理后台展示）。"""
        channels = self._config.get("channels", {})
        result: List[ChannelConfig] = []
        for provider in VALID_PROVIDERS:
            raw = channels.get(provider, {})
            result.append(
                ChannelConfig(
                    provider=provider,
                    enabled=raw.get("enabled", False),
                    appid=raw.get("appid"),
                    app_secret=raw.get("app_secret"),
                    callback_url=raw.get("callback_url"),
                )
            )
        return result

    def get_channel_status_list(self) -> List[ChannelStatus]:
        """返回全部 4 个通道的状态（供前端按钮渲染）。"""
        channels = self._config.get("channels", {})
        return [
            ChannelStatus(
                provider=p,
                display_name=PROVIDER_DISPLAY_NAMES[p],
                enabled=channels.get(p, {}).get("enabled", False),
            )
            for p in VALID_PROVIDERS
        ]

    # ---------- 写入 ----------

    def save_channels(self, channel_configs: List[ChannelConfig]) -> None:
        """保存管理员提交的通道配置。"""
        channels: Dict[str, Any] = self._config.get("channels", {})
        for ch in channel_configs:
            existing = channels.get(ch.provider, {})
            existing["enabled"] = ch.enabled
            if ch.appid is not None:
                existing["appid"] = ch.appid
            if ch.app_secret is not None:
                existing["app_secret"] = ch.app_secret
            if ch.callback_url is not None:
                existing["callback_url"] = ch.callback_url
            channels[ch.provider] = existing
        self._config["channels"] = channels
        # 同步 enabled_channels 列表
        self._config["enabled_channels"] = [
            p for p, cfg in channels.items() if cfg.get("enabled")
        ]


def mask_secret(secret: Optional[str]) -> Optional[str]:
    """对 secret 脱敏：只显示前 4 位 + ****。"""
    if not secret:
        return None
    if len(secret) <= 4:
        return "****"
    return secret[:4] + "****"
