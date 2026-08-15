"""deepDDW MCP 资源注册表（开源裁剪版）。

暴露（白名单组件）：
- ddw://knowledge-bases         知识库列表（SQLite）
- ddw://plugins                 插件列表（白名单插件）

商业资源（training/courses、hris/adapters、客服等）已随插件移除。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Resource:
    uri: str
    name: str
    description: str = ""
    mime_type: str = "application/json"
    handler: Optional[Callable[[Dict[str, Any]], Awaitable[Any]]] = None

    def to_mcp(self) -> Dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mime_type,
        }


class ResourceRegistry:
    def __init__(self) -> None:
        self._resources: Dict[str, Resource] = {}

    def register(self, resource: Resource) -> None:
        if resource.uri in self._resources:
            logger.warning("resource %s already registered, override", resource.uri)
        self._resources[resource.uri] = resource
        logger.info("registered resource %s", resource.uri)

    def unregister(self, uri: str) -> None:
        self._resources.pop(uri, None)

    def list(self) -> List[Resource]:
        return list(self._resources.values())

    async def read(self, uri: str, context: Optional[Dict[str, Any]] = None) -> Any:
        r = self._resources.get(uri)
        if r is None:
            return {"error": {"code": -32001, "message": f"resource not found: {uri}"}}
        if r.handler is None:
            return {"error": {"code": -32603, "message": f"resource {uri} has no handler"}}
        try:
            return await r.handler(context or {})
        except Exception as e:  # noqa: BLE001
            logger.exception("resource %s read failed", uri)
            return {"error": {"code": -32603, "message": f"resource read failed: {e}"}}


def install_default_resources(registry: ResourceRegistry) -> None:
    async def knowledge_bases(ctx):
        from core.knowledge import get_conn

        try:
            conn = get_conn()
            try:
                rows = conn.execute(
                    "SELECT id, title FROM kb_documents ORDER BY id LIMIT 50"
                ).fetchall()
                items = [{"id": r["id"], "name": r["title"]} for r in rows]
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("knowledge-bases resource degraded: %s", exc)
            items = []
        return {
            "uri": "ddw://knowledge-bases",
            "mimeType": "application/json",
            "text": str(items),
        }

    async def plugins(ctx):
        return {
            "uri": "ddw://plugins",
            "mimeType": "application/json",
            "text": (
                '[{"name":"ddw-docs-portal","version":"0.1.0","license":"free"},'
                '{"name":"ddw-searxng","version":"0.1.0","license":"free"}]'
            ),
        }

    registry.register(Resource(
        uri="ddw://knowledge-bases",
        name="deepDDW 知识库列表",
        description="个人级知识库中的全部文档标题",
        handler=knowledge_bases,
    ))
    registry.register(Resource(
        uri="ddw://plugins",
        name="deepDDW 插件列表",
        description="deepDDW 白名单插件元信息",
        handler=plugins,
    ))


__all__ = ["Resource", "ResourceRegistry", "install_default_resources"]
