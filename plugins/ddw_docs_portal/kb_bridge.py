"""文档检索桥接（deepDDW 开源裁剪版）。

以 duck-typing ``search(query, top_k)`` 返回 [{content, source, score}]，
供外部检索方（如聚合搜索/客服链路，若有）并联调用。

安全边界：匿名场景只检索 public 文档（deepDDW 单用户默认即 public 可见集合）。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# portal_search_fn 签名: async (query: str, top_k: int) -> List[dict]
# 每项: {content, slug, version, score, doc_title, ...}
PortalSearchFn = Callable[[str, int], Any]


class DocsKbBridge:
    """组合检索器：并联 docs_portal（仅 public 文档）。"""

    def __init__(self, portal_search_fn: PortalSearchFn) -> None:
        self._portal_search = portal_search_fn

    async def search(self, query: str, top_k: int = 4) -> list[dict[str, Any]]:
        """返回 [{content, source, score}]，source 以 `docs:` 前缀标记来自文档栏目。"""
        try:
            docs = await self._portal_search(query, top_k)
        except Exception as exc:  # noqa: BLE001
            logger.warning("kb_bridge: docs portal search failed: %s", exc)
            return []
        results = []
        for d in docs or []:
            results.append(
                {
                    "content": d.get("excerpt") or d.get("content", ""),
                    "source": f"docs:{d.get('slug', '')}",
                    "score": float(d.get("score") or 0.0),
                }
            )
        return results


def build_kb_bridge(portal_search_fn: PortalSearchFn) -> DocsKbBridge:
    """构造文档桥接检索器。"""
    return DocsKbBridge(portal_search_fn)


async def default_public_search(query: str, top_k: int = 4) -> list[dict[str, Any]]:
    """默认实现：只搜 public 文档（匿名/无身份场景）。"""
    from core.database.session import session_scope

    from .services import DocsPortalService

    user = {"tenant_id": 0, "user_id": 0, "role": "member"}
    async with session_scope() as db:
        svc = DocsPortalService(db)
        result = await svc.search_docs(query, top_k, user)
    return result.get("sources", [])


__all__ = ["DocsKbBridge", "build_kb_bridge", "default_public_search"]


__all__ = ["DocsKbBridge", "build_kb_bridge", "default_public_search"]
