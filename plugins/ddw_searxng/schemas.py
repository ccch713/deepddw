"""DDW SearXNG 插件 Pydantic schemas。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SearchResult(BaseModel):
    """单条搜索结果。"""

    title: str
    url: str
    content: str = ""
    engine: str = ""
    score: float = 0.0


class SearchResp(BaseModel):
    """搜索响应。"""

    success: bool
    data: List[SearchResult] = []
    total: int = 0
    elapsed_ms: int = 0
    unresponsive_engines: List[List[str]] = []
    error: Optional[str] = None
    detail: Optional[str] = None


class HealthResp(BaseModel):
    """健康检查响应。"""

    ok: bool
    searxng_url: str
    engines: Dict[str, Any] = {}
    detail: Optional[str] = None


__all__ = ["HealthResp", "SearchResp", "SearchResult"]
