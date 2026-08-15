"""deepDDW MCP Server 核心（开源裁剪版）。

支持的方法（JSON-RPC 2.0）：
- ``initialize``               握手
- ``ping``                     健康检查
- ``tools/list``               列出工具（仅白名单工具，license 分层过滤）
- ``tools/call``               调用工具
- ``resources/list``           列出资源
- ``resources/read``           读取资源

deepDDW 工具分层：``tools/list`` 只暴露白名单插件（core / ddw-docs-portal /
ddw-searxng）注册的工具——commercial 插件工具绝不注册/绝不外露（P0-1 验收项）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from core.mcp.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    RESOURCE_NOT_FOUND,
    SERVER_CAPABILITIES,
    SERVER_INFO,
    TOOL_NOT_FOUND,
    JsonRpcRequest,
    make_error_resp,
    make_result,
    negotiate_protocol_version,
)
from core.mcp.resources import ResourceRegistry, install_default_resources
from core.mcp.tools import ToolRegistry, install_default_tools

logger = logging.getLogger(__name__)

# deepDDW 白名单：tools/list 只暴露这些来源的工具（commercial 插件工具绝不注册）
WHITELIST_PLUGIN_NAMES = frozenset({"core", "ddw-docs-portal", "ddw-searxng"})


class DDWMCPServer:
    def __init__(self) -> None:
        self.tools = ToolRegistry()
        self.resources = ResourceRegistry()
        install_default_tools(self.tools)
        install_default_resources(self.resources)
        self.initialized = False

    # ------------------------------------------------------------------ #
    # 入口
    # ------------------------------------------------------------------ #

    async def handle_request(self, request: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """处理一个 JSON-RPC 2.0 请求 dict，返回响应 dict。"""
        try:
            req = self._parse(request)
        except ValueError as e:
            return make_error_resp(request.get("id"), PARSE_ERROR, f"parse error: {e}").to_dict()

        if req is None:
            return make_error_resp(None, INVALID_REQUEST, "invalid request").to_dict()

        method = req.method
        params = req.params or {}

        try:
            if method == "initialize":
                return self._handle_initialize(req, params).to_dict()
            if method == "ping":
                return make_result(req.id, {"ok": True}).to_dict()
            if method == "tools/list":
                return make_result(req.id, {"tools": [t.to_mcp() for t in self.public_tools()]}).to_dict()
            if method == "tools/call":
                name = params.get("name")
                arguments = params.get("arguments") or {}
                if not name:
                    return make_error_resp(req.id, INVALID_PARAMS, "missing tool name").to_dict()
                tool = self.tools.get(name)
                if tool is None or tool.plugin_name not in WHITELIST_PLUGIN_NAMES:
                    return make_error_resp(req.id, TOOL_NOT_FOUND, f"tool not found: {name}").to_dict()
                result = await tool.handler(arguments, context or {})
                return make_result(req.id, result).to_dict()
            if method == "resources/list":
                return make_result(req.id, {"resources": [r.to_mcp() for r in self.resources.list()]}).to_dict()
            if method == "resources/read":
                uri = params.get("uri")
                if not uri:
                    return make_error_resp(req.id, INVALID_PARAMS, "missing resource uri").to_dict()
                if uri not in {r.uri for r in self.resources.list()}:
                    return make_error_resp(req.id, RESOURCE_NOT_FOUND, f"resource not found: {uri}").to_dict()
                content = await self.resources.read(uri, context)
                return make_result(req.id, content).to_dict()
            # 通知（无 id）：返回 None 让上层不发响应
            if req.id is None:
                logger.debug("notification: %s", method)
                return None  # type: ignore[return-value]
            return make_error_resp(req.id, METHOD_NOT_FOUND, f"method not found: {method}").to_dict()
        except Exception as e:  # noqa: BLE001
            logger.exception("MCP handler failed: %s", method)
            return make_error_resp(req.id, INTERNAL_ERROR, f"internal error: {e}").to_dict()

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #

    def public_tools(self):
        """白名单过滤后的工具列表（经典端点 tools/list 与 streamable-http 共用）。"""
        return [
            t for t in self.tools.list()
            if t.plugin_name in WHITELIST_PLUGIN_NAMES
        ]

    def _parse(self, raw: Any) -> Optional[JsonRpcRequest]:
        if not isinstance(raw, dict):
            raise ValueError("request must be an object")
        if raw.get("jsonrpc") != "2.0":
            raise ValueError("jsonrpc must be '2.0'")
        method = raw.get("method")
        if not isinstance(method, str) or not method:
            raise ValueError("missing method")
        params = raw.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        return JsonRpcRequest(
            jsonrpc="2.0",
            id=raw.get("id"),
            method=method,
            params=params,
        )

    # type: ignore[return-value]
    def _handle_initialize(self, req: JsonRpcRequest, params: Dict[str, Any]) -> Any:
        self.initialized = True
        # v6.0 双协议：版本协商（客户端请求版本受支持则返回，否则返回最高版）
        requested = (params or {}).get("protocolVersion")
        negotiated = negotiate_protocol_version(requested)
        logger.info(
            "mcp initialize: requested=%s → negotiated=%s",
            requested,
            negotiated,
        )
        return make_result(req.id, {
            "protocolVersion": negotiated,
            "serverInfo": SERVER_INFO,
            "capabilities": SERVER_CAPABILITIES,
        })


_server: Optional[DDWMCPServer] = None


def get_mcp_server() -> DDWMCPServer:
    global _server
    if _server is None:
        _server = DDWMCPServer()
    return _server


__all__ = ["DDWMCPServer", "get_mcp_server"]
