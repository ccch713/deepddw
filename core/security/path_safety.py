"""DDW 路径净化（§2.3）

技术规范 v1.0 §2.3：所有文件操作前必须经过 8 道防线。
"""
from __future__ import annotations

import os
import unicodedata
from pathlib import Path


class PathSafetyError(ValueError):
    """路径校验失败时抛出。"""


_MAX_PATH_LENGTH = 2000


def sanitize_path(path: str | os.PathLike, base_dir: str | os.PathLike) -> Path:
    """8 道防线校验路径安全。

    Args:
        path: 待校验的路径
        base_dir: 允许的根目录

    Returns:
        解析后的绝对路径（保证在 base_dir 内）

    Raises:
        PathSafetyError: 任何一道防线失败
    """
    if isinstance(path, os.PathLike):
        path = os.fspath(path)
    if isinstance(base_dir, os.PathLike):
        base_dir = os.fspath(base_dir)

    # 防线 1: null byte 拒绝
    if "\0" in path:
        raise PathSafetyError("路径包含 null byte")

    # 防线 2: URL 编码遍历拒绝
    lowered = path.lower()
    if "%2e%2e" in lowered or "%2f" in lowered or "%5c" in lowered:
        raise PathSafetyError("URL 编码遍历攻击")

    # 防线 3: Unicode NFKC 归一化攻击
    normalized = unicodedata.normalize("NFKC", path)
    if ".." in normalized.replace("\\", "/").split("/"):
        # 仅当归一化后产生 .. 才拒绝
        if ".." in Path(normalized).parts:
            raise PathSafetyError("Unicode 归一化路径遍历攻击")

    # 防线 4: 反斜杠拒绝（仅允许正斜杠或系统默认）
    if "\\" in path:
        raise PathSafetyError("路径包含反斜杠")

    # 防线 5: 绝对路径拒绝（相对 base_dir）
    p = Path(path)
    if p.is_absolute():
        raise PathSafetyError("不允许绝对路径")

    # 防线 6: 路径中包含 .. 拒绝
    if ".." in p.parts:
        raise PathSafetyError("路径包含 ..")

    # 防线 7: 路径长度
    full = (Path(base_dir) / p)
    if len(str(full)) > _MAX_PATH_LENGTH:
        raise PathSafetyError(f"路径超过 {_MAX_PATH_LENGTH} 字符")

    # 防线 8: 拼接后必须位于 base 内
    try:
        full_resolved = full.resolve()
        base_resolved = Path(base_dir).resolve()
    except OSError as e:
        raise PathSafetyError(f"路径解析失败: {e}") from e

    try:
        full_resolved.relative_to(base_resolved)
    except ValueError as e:
        raise PathSafetyError("路径超出 base_dir 范围") from e

    return full_resolved
