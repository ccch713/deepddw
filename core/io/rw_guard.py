"""DDW Read-Before-Write 强制（§2.5）

技术规范 v1.0 §2.5：任何写入前必须先有对应的读记录。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import time
from dataclasses import dataclass


@dataclass
class ReadRecord:
    """读记录。"""
    path: str
    mtime: float
    sha256: str
    read_at: float


class RWGuard:
    """读后写守卫。"""

    def __init__(self) -> None:
        self._reads: dict[str, ReadRecord] = {}
        self._lock = asyncio.Lock()

    async def record_read(self, path: str) -> ReadRecord:
        """记录一次读取（应通过 ReadCache.get_or_load 自动调用）。"""
        try:
            stat = os.stat(path)
        except OSError:
            raise FileNotFoundError(f"无法 stat: {path}")

        # 读取内容计算 sha256（小文件适用）
        sha = ""
        try:
            if stat.st_size < 1_000_000:  # < 1MB 才计算 hash
                with open(path, "rb") as f:
                    sha = hashlib.sha256(f.read()).hexdigest()
        except OSError:
            pass

        record = ReadRecord(
            path=path,
            mtime=stat.st_mtime,
            sha256=sha,
            read_at=time.time(),
        )
        async with self._lock:
            self._reads[path] = record
        return record

    async def check_write(self, path: str) -> tuple[bool, str]:
        """检查是否可以写入。

        Returns:
            (allowed, reason) — allowed=True 时可写
        """
        # 文件不存在 → 视为新文件创建（无需读记录）
        try:
            os.stat(path)
        except OSError:
            return True, "文件不存在，视为创建"

        async with self._lock:
            record = self._reads.get(path)
            if record is None:
                return False, "无读记录"

            # 检查 mtime 一致性
            try:
                current_mtime = os.stat(path).st_mtime
            except OSError:
                return True, "文件不存在，视为创建"

            if abs(current_mtime - record.mtime) > 0.001:
                return False, f"mtime 已变 (读时 {record.mtime}, 当前 {current_mtime})"

        return True, "OK"

    async def invalidate_read(self, path: str) -> None:
        """写入后强制失效读记录。"""
        async with self._lock:
            self._reads.pop(path, None)

    async def has_read(self, path: str) -> bool:
        async with self._lock:
            return path in self._reads
