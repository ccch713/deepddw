"""DDW Open-redirect 防御（技术规范 §5.2）

强制 same-hostname-only 重定向。
"""
from __future__ import annotations

from urllib.parse import urlparse


class RedirectGuardError(ValueError):
    """重定向目标非法时抛出。"""


def is_safe_redirect(
    original_url: str,
    redirect_url: str,
    allowed_extra_hosts: set[str] | None = None,
) -> bool:
    """检查重定向 URL 是否同主机。

    Args:
        original_url: 原始请求 URL
        redirect_url: 重定向目标 URL
        allowed_extra_hosts: 显式允许的额外主机（默认空）

    Returns:
        True = 安全，False = 应拒绝
    """
    orig = urlparse(original_url)
    redir = urlparse(redirect_url)

    # 协议必须一致
    if orig.scheme != redir.scheme:
        return False

    # 主机名必须完全相等（或去除 www. 前缀后相等）
    orig_host = (orig.hostname or "").lower()
    redir_host = (redir.hostname or "").lower()

    # 主机名匹配（去除 www.）
    orig_stripped = orig_host.removeprefix("www.")
    redir_stripped = redir_host.removeprefix("www.")

    # 主机名不同 → 不安全
    if orig_stripped != redir_stripped:
        # 显式允许列表
        if allowed_extra_hosts and redir_host in allowed_extra_hosts:
            # 但仍要查端口
            pass
        else:
            return False

    # 主机名相同 → 检查端口必须一致（防 a.com:443 → a.com:8080）
    if (orig.port or 0) != (redir.port or 0):
        return False

    return True


def assert_safe_redirect(
    original_url: str,
    redirect_url: str,
    allowed_extra_hosts: set[str] | None = None,
) -> None:
    """强制同主机重定向检查。"""
    if not is_safe_redirect(original_url, redirect_url, allowed_extra_hosts):
        raise RedirectGuardError(
            f"重定向被拒绝: {original_url} → {redirect_url}"
        )
