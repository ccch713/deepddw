"""DDW SearXNG 插件服务层。

SearXNG HTTP 客户端：search / health，超时 15s，不可达抛 SearXNGUnavailable。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

SEARXNG_URL = os.environ.get("SEARXNG_URL", "http://127.0.0.1:8888")


class SearXNGUnavailable(Exception):
    """SearXNG 服务不可达或超时。"""


def _normalize(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将 SearXNG 结果归一化为标准格式。"""
    normalized = []
    for r in results:
        normalized.append(
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", ""),
                "engine": r.get("engine", ""),
                "score": r.get("score", 0.0),
            }
        )
    return normalized


async def search(
    query: str,
    limit: int = 5,
    engines: Optional[str] = None,
) -> Dict[str, Any]:
    """调用 SearXNG 搜索 API。

    Returns:
        {data: [...], total, elapsed_ms, unresponsive_engines}

    Raises:
        SearXNGUnavailable: SearXNG 不可达或超时。
    """
    params: Dict[str, Any] = {"q": query, "format": "json"}
    if engines:
        params["engines"] = engines

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{SEARXNG_URL}/search", params=params)
            resp.raise_for_status()
            body = resp.json()
    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
        raise SearXNGUnavailable(f"SearXNG 不可达: {e}") from e

    elapsed_ms = int((time.monotonic() - start) * 1000)
    raw_results = body.get("results", [])
    data = _normalize(raw_results)[:limit]

    return {
        "data": data,
        "total": len(data),
        "elapsed_ms": elapsed_ms,
        "unresponsive_engines": body.get("unresponsive_engines", []),
    }


async def health() -> Dict[str, Any]:
    """健康检查：尝试调用 SearXNG search 端点。

    Returns:
        {ok: bool, searxng_url, engines: {...}, detail?}
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{SEARXNG_URL}/search",
                params={"q": "test", "format": "json"},
            )
            resp.raise_for_status()
            body = resp.json()

        engines_info: Dict[str, Any] = {}
        for r in body.get("results", []):
            eng = r.get("engine", "")
            if eng and eng not in engines_info:
                engines_info[eng] = True

        return {
            "ok": True,
            "searxng_url": SEARXNG_URL,
            "engines": engines_info,
        }
    except Exception as e:
        return {
            "ok": False,
            "searxng_url": SEARXNG_URL,
            "engines": {},
            "detail": str(e),
        }


__all__ = ["SearXNGUnavailable", "health", "search"]
