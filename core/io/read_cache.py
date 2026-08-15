"""DDW Read Dedup 缓存（§2.4）

技术规范 v1.0 §2.4：(path, mtime, offset, limit) 四元组缓存。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class ReadKey:
    """读取缓存 key。"""
    path: str
    mtime: float
    offset: int
    limit: int | None  # None = 全文


@dataclass
class CacheEntry:
    """缓存条目。"""
    content: str
    created_at: float
    hits: int = 0


class ReadCache:
    """读取去重缓存。"""

    def __init__(self, max_entries: int = 256, ttl_seconds: float = 300.0) -> None:
        self._store: dict[ReadKey, CacheEntry] = {}
        self._max = max_entries
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    async def get_or_load(
        self,
        path: str,
        load_fn,
        offset: int = 0,
        limit: int | None = None,
    ) -> tuple[str, bool]:
        """读取文件，缓存命中返回 (content, hit=True)，未命中 load 后写入。"""
        try:
            stat = os.stat(path)
        except OSError:
            raise FileNotFoundError(f"无法 stat 文件: {path}")

        key = ReadKey(path=path, mtime=stat.st_mtime, offset=offset, limit=limit)
        async with self._lock:
            entry = self._store.get(key)
            if entry and (time.time() - entry.created_at) < self._ttl:
                entry.hits += 1
                self._hits += 1
                return entry.content, True

            # miss: 加载并写入
            self._misses += 1
            content = load_fn(path, offset, limit)
            self._evict_if_full()
            self._store[key] = CacheEntry(content=content, created_at=time.time())
            return content, False

    def invalidate(self, path: str) -> int:
        """使某路径的所有缓存条目失效。返回失效条数。"""
        to_del = [k for k in self._store if k.path == path]
        for k in to_del:
            del self._store[k]
        return len(to_del)

    def _evict_if_full(self) -> None:
        if len(self._store) >= self._max:
            # LRU 简化：按 created_at 删除最早的
            oldest = min(self._store.items(), key=lambda x: x[1].created_at)
            del self._store[oldest[0]]

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total else 0.0

    def fingerprint(self) -> str:
        """生成缓存状态指纹（用于诊断）。"""
        return hashlib.sha256(
            str(sorted(k.path for k in self._store)).encode()
        ).hexdigest()[:16]
