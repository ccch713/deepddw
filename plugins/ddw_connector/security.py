"""DDW 连接器凭据密文存储（安全硬伤修复：conn_info 不再明文落库）。

conn_info 含数据源连接串/密码/令牌，禁止明文存储。
使用 Fernet（AES-128-CBC + HMAC-SHA256）对称加密：

- 密钥来自环境变量 ``DDW_CONNECTOR_ENC_KEY``（base64 urlsafe 32 字节，
  生成：``python -c "from cryptography.fernet import Fernet;
  print(Fernet.generate_key().decode())"``）
- 未配置密钥时拒绝写入（fail-secure），绝不降级为明文存储
- 解密失败（密钥不匹配/数据损坏）抛 ``ValueError`` 并给出明确提示

密钥只在部署环境变量中注入，代码/仓库/日志不出现任何密钥。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# 加密密钥环境变量名（管理端/部署端注入，格式：Fernet base64 urlsafe key）
ENV_KEY_NAME = "DDW_CONNECTOR_ENC_KEY"

_MISSING_KEY_MESSAGE = (
    f"未配置 {ENV_KEY_NAME}，无法安全存储数据源凭据（拒绝明文落库）。"
    '请先生成密钥：python -c "from cryptography.fernet import Fernet; '
    'print(Fernet.generate_key().decode())" 并 export 到部署环境。'
)


def _get_fernet() -> Fernet:
    """加载 Fernet 实例；未配置或格式非法抛 ValueError（fail-secure）。"""
    import os

    key = os.environ.get(ENV_KEY_NAME, "").strip()
    if not key:
        raise ValueError(_MISSING_KEY_MESSAGE)
    try:
        return Fernet(key)
    except (ValueError, TypeError) as e:
        raise ValueError(f"{ENV_KEY_NAME} 格式无效（应为 Fernet key）: {e}") from e


def encrypt_conn_info(conn_info: Dict[str, Any]) -> str:
    """加密连接信息：JSON 序列化 → Fernet 加密 → 返回字符串 token。"""
    payload = json.dumps(conn_info, ensure_ascii=False).encode("utf-8")
    token = _get_fernet().encrypt(payload)
    return token.decode("utf-8")


def decrypt_conn_info(token: str) -> Dict[str, Any]:
    """解密连接信息 token → dict。解密失败抛 ValueError（含密钥不匹配提示）。"""
    try:
        payload = _get_fernet().decrypt(token.encode("utf-8"))
    except InvalidToken as e:
        raise ValueError(
            "数据源凭据解密失败（DDW_CONNECTOR_ENC_KEY 不匹配或数据损坏）"
        ) from e
    return json.loads(payload.decode("utf-8"))


__all__ = ["ENV_KEY_NAME", "encrypt_conn_info", "decrypt_conn_info"]
