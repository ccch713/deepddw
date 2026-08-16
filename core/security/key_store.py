"""API Key 安全存储（P1-9：Fernet 加密落盘，yaml 只存密文）。

- 本地主密钥文件 ``data/.deepddw_master.key``（权限 600，首次生成）；
- ``encrypt_secret`` 用 Fernet 加密 → 密文写 config/deployment.yaml；
- ``decrypt_secret`` 解密读取；**兼容降级**：非 Fernet 密文（旧明文配置）
  原样返回（升级路径不破坏已有部署），但新写入一律加密。

安全属性：
- key 明文不落盘（yaml 只存密文）；
- GET /api/v1/llm/config 仍只回布尔，不涉及本模块；
- 主密钥文件权限 600，与数据目录同机。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MASTER_KEY_FILE = Path("data/.deepddw_master.key")
_FERNET_PREFIX = "gAAAA"  # Fernet token 固定前缀（用于识别密文/明文）


def _master_key() -> bytes:
    """读取或生成主密钥（权限 600）。"""
    key_path = _MASTER_KEY_FILE
    key_path.parent.mkdir(parents=True, exist_ok=True)
    if key_path.exists():
        return key_path.read_bytes()
    from cryptography.fernet import Fernet

    key = Fernet.generate_key()
    key_path.write_bytes(key)
    try:
        os.chmod(key_path, 0o600)
    except OSError as exc:  # noqa: BLE001
        logger.warning("chmod master key failed: %s", exc)
    return key


def encrypt_secret(plaintext: str) -> str:
    """加密明文 → Fernet token 字符串。"""
    from cryptography.fernet import Fernet

    return Fernet(_master_key()).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    """解密 Fernet token；非密文（旧明文配置）原样返回（兼容降级）。

    解密失败（密钥更换等）返回空串并告警——绝不把解密异常抛给调用方
    （避免 LLM 调用链被打断）。
    """
    if not value:
        return ""
    if not value.startswith(_FERNET_PREFIX):
        return value  # 旧明文配置兼容
    try:
        from cryptography.fernet import Fernet, InvalidToken

        return Fernet(_master_key()).decrypt(value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:  # noqa: BLE001
        logger.warning("secret decrypt failed (key rotated?): %s", exc)
        return ""


def is_encrypted(value: str) -> bool:
    """是否为 Fernet 密文。"""
    return bool(value) and value.startswith(_FERNET_PREFIX)


def decrypt_optional(value: Optional[str]) -> str:
    """对 Optional[str] 的便捷解密（None → ""）。"""
    return decrypt_secret(value or "")


__all__ = ["encrypt_secret", "decrypt_secret", "decrypt_optional", "is_encrypted"]
