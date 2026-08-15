"""DDW MCP 资源注册表（DDW AI Hub v5.4 — 模块 D1）。

暴露：
- ddw://knowledge-bases         知识库列表
- ddw://plugins                 插件列表
- ddw://training/courses        培训课程
- ddw://hris/adapters           HRIS 适配器清单
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
        return {
            "uri": "ddw://knowledge-bases",
            "mimeType": "application/json",
            "text": '[{"id":1,"name":"企业公共知识库"},{"id":2,"name":"客服知识库-A"}]',
        }

    async def plugins(ctx):
        return {
            "uri": "ddw://plugins",
            "mimeType": "application/json",
            "text": '[{"name":"customer-service","version":"2.0.0"},{"name":"ddw-training","version":"0.1.0"}]',
        }

    async def training_courses(ctx):
        return {
            "uri": "ddw://training/courses",
            "mimeType": "application/json",
            "text": '[{"id":"physics-g9","subject":"physics","grade":"9"},{"id":"chemistry-g9","subject":"chemistry","grade":"9"}]',
        }

    async def hris_adapters(ctx):
        return {
            "uri": "ddw://hris/adapters",
            "mimeType": "application/json",
            "text": '[{"name":"kingdee"},{"name":"wecom"},{"name":"beisen"},{"name":"feishu"},{"name":"dingtalk"}]',
        }

    registry.register(Resource(
        uri="ddw://knowledge-bases",
        name="DDW 知识库列表",
        description="所有可见的知识库（按权限过滤）",
        handler=knowledge_bases,
    ))
    registry.register(Resource(
        uri="ddw://plugins",
        name="DDW 插件列表",
        description="已注册的 DDW 插件元信息",
        handler=plugins,
    ))
    registry.register(Resource(
        uri="ddw://training/courses",
        name="DDW 培训课程",
        description="培训插件的全部课程配置",
        handler=training_courses,
    ))
    registry.register(Resource(
        uri="ddw://hris/adapters",
        name="HRIS 适配器清单",
        description="所有可用的 HRIS 适配器元信息",
        handler=hris_adapters,
    ))


__all__ = ["Resource", "ResourceRegistry", "install_default_resources"]
