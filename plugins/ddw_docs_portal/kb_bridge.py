"""客服知识库桥接（kb_bridge，决策 3 客服侧）。

ddw_online_cs 检索时并入文档栏目结果：以组合检索器（duck-typing `search(query, top_k)`）
返回与客服 KB 相同结构 [{content, source, score}]，chat/chat_stream 检索段并联调用即可。

安全边界：客服场景无用户会话 → 只检索平台级 public 文档（tenant_id=0 可见集合），
绝不暴露 tenant 级文档（决策 1 红线）。
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# portal_search_fn 签名: async (query: str, top_k: int) -> List[dict]
# 每项: {content, slug, version, score, doc_title, ...}
PortalSearchFn = Callable[[str, int], Any]


class DocsKbBridge:
    """组合检索器：客服 KB 之外并联 docs_portal（仅 public 文档）。"""

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
                    "content": d.get("content", ""),
                    "source": f"docs:{d.get('slug', '')}",
                    "score": float(d.get("score") or 0.0),
                }
            )
        return results


def build_kb_bridge(portal_search_fn: PortalSearchFn) -> DocsKbBridge:
    """构造客服-文档桥接检索器。"""
    return DocsKbBridge(portal_search_fn)


async def default_public_search(query: str, top_k: int = 4) -> list[dict[str, Any]]:
    """默认实现：只搜平台级 public 文档（客服场景无租户身份）。

    供 ddw_online_cs 检索段直接调用；不依赖请求上下文。
    """
    from core.database.session import session_scope
    from core.database.tenant_filter import bypass_tenant_filter

    from .services import DocsPortalService

    user = {"tenant_id": 0, "user_id": 0, "role": "member"}
    async with session_scope() as db, bypass_tenant_filter():
        svc = DocsPortalService(db)
        result = await svc.search_docs(query, top_k, user)
    return result.get("sources", [])


__all__ = ["DocsKbBridge", "build_kb_bridge", "default_public_search"]
