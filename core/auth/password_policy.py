"""密码强度策略（DDW AI Hub 密码生命周期补丁）。

统一校验注册与改密场景的密码强度：
- 长度 ≥ 8
- 必须含字母 + 数字
- 不能纯字母 / 纯数字
- 不能全部相同字符或连续递增/递减
- 不在常见弱密码表中
"""

from __future__ import annotations

from typing import Optional

# 常见弱密码表
WEAK_PASSWORDS: set[str] = {
    "12345678", "87654321", "password", "passw0rd", "qwertyui", "asdfghjk",
    "zxcvbnm,", "admin123", "123456789", "11111111", "abcdefgh", "abcd1234",
    "00000000", "123123123", "a1234567", "abc12345", "66666666", "88888888",
}


def validate_password_strength(pwd: str) -> Optional[str]:
    """校验密码强度。

    Returns:
        None 表示通过；否则返回中文错误描述。
    """
    if len(pwd) < 8:
        return "密码长度不能少于 8 位"

    has_alpha = any(c.isalpha() for c in pwd)
    has_digit = any(c.isdigit() for c in pwd)

    if not has_alpha:
        return "密码必须包含字母"
    if not has_digit:
        return "密码必须包含数字"

    if pwd.isalpha():
        return "密码不能为纯字母"
    if pwd.isdigit():
        return "密码不能为纯数字"

    # 全部相同字符（如 11111111 / aaaaaaaa）
    if len(set(pwd)) == 1:
        return "密码不能为全部相同字符"

    # 连续递增/递减（如 12345678 / abcdefgh / 87654321）
    lower = pwd.lower()
    if _is_sequential(lower):
        return "密码不能为连续递增或递减字符"

    if pwd.lower() in {w.lower() for w in WEAK_PASSWORDS}:
        return "该密码过于常见，请更换"

    return None


def _is_sequential(s: str) -> bool:
    """检查字符串是否为连续递增或递减序列。"""
    if len(s) < 4:
        return False
    # 连续递增
    inc = all(ord(s[i + 1]) - ord(s[i]) == 1 for i in range(len(s) - 1))
    # 连续递减
    dec = all(ord(s[i]) - ord(s[i + 1]) == 1 for i in range(len(s) - 1))
    return inc or dec
