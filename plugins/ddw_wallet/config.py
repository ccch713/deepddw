"""ddw_wallet 配置：全部从环境变量读取，禁止硬编码密钥。"""
from __future__ import annotations

import os


class WalletSettings:
    """环境变量驱动的钱包配置。"""

    # 微信支付
    WECHAT_MCH_ID: str = os.getenv(
        "DDW_WALLET_WECHAT_MCH_ID", ""
    )
    WECHAT_APP_ID: str = os.getenv(
        "DDW_WALLET_WECHAT_APP_ID", ""
    )
    WECHAT_API_V3_KEY: str = os.getenv(
        "DDW_WALLET_WECHAT_API_V3_KEY", ""
    )
    WECHAT_PRIVATE_KEY: str = os.getenv(
        "DDW_WALLET_WECHAT_PRIVATE_KEY", ""
    )
    WECHAT_CERT: str = os.getenv(
        "DDW_WALLET_WECHAT_CERT", ""
    )
    WECHAT_CERT_SERIAL_NO: str = os.getenv(
        "DDW_WALLET_WECHAT_CERT_SERIAL_NO", ""
    )
    WECHAT_PUBLIC_KEY_ID: str = os.getenv(
        "DDW_WALLET_WECHAT_PUBLIC_KEY_ID", ""
    )
    WECHAT_PUBLIC_KEY: str = os.getenv(
        "DDW_WALLET_WECHAT_PUBLIC_KEY", ""
    )
    WECHAT_NOTIFY_URL: str = os.getenv(
        "DDW_WALLET_WECHAT_NOTIFY_URL", ""
    )

    # 支付宝
    ALIPAY_APP_ID: str = os.getenv(
        "DDW_WALLET_ALIPAY_APP_ID", ""
    )
    ALIPAY_PRIVATE_KEY: str = os.getenv(
        "DDW_WALLET_ALIPAY_PRIVATE_KEY", ""
    )
    ALIPAY_PUBLIC_KEY: str = os.getenv(
        "DDW_WALLET_ALIPAY_PUBLIC_KEY", ""
    )
    ALIPAY_NOTIFY_URL: str = os.getenv(
        "DDW_WALLET_ALIPAY_NOTIFY_URL", ""
    )

    # 数据库
    DB_URL: str = os.getenv(
        "DDW_WALLET_DB_URL", "sqlite+aiosqlite:///ddw_wallet.db"
    )


settings = WalletSettings()

__all__ = ["settings", "WalletSettings"]
