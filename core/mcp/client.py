"""DDW MCP Client — 连接外部 MCP Server 的桥接层。

参照 Proma 的 PiMcpClientManager 设计，让 DDW 插件可以：
  * 通过 stdio / http / sse 三种 transport 连接外部 MCP Server
  * 自动管理连接生命周期（缓存、重连、释放）
  * 将 MCP tool 转换为 DDW ToolRegistry 可直接调用的格式

使用示例::

    from core.mcp.client import MCPClientManager

    manager = MCPClientManager()
    tools = await manager.list_tools("my-server", {"type": "stdio", "command": "npx", "args": ["-y", "@example/mcp-server"]})
    result = await manager.call_tool("my-server", "tool_name", {"arg": "value"})
    await manager.dispose()
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
#  MCP Server 配置
# --------------------------------------------------------------------------- #


class MCPServerConfig:
    """MCP Server 连接配置。

    对应 mcp.json 中的单个 server 条目。

    Supported types:
        - ``stdio``: 启动子进程，通过 stdin/stdout 通信
        - ``http``: Streamable HTTP transport
        - ``sse``: Server-Sent Events transport
    """

    def __init__(
        self,
        *,
        type: str = "stdio",
        command: Optional[str] = None,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        startup_timeout_sec: float = 30.0,
        request_timeout_sec: float = 60.0,
    ) -> None:
        self.type = type
        self.command = command
        self.args = args or []
        self.env = env
        self.url = url
        self.headers = headers
        self.startup_timeout_sec = startup_timeout_sec
        self.request_timeout_sec = request_timeout_sec

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPServerConfig":
        return cls(
            type=data.get("type", "stdio"),
            command=data.get("command"),
            args=data.get("args"),
            env=data.get("env"),
            url=data.get("url"),
            headers=data.get("headers"),
            startup_timeout_sec=data.get("startup_timeout_sec", data.get("timeout", 30)),
            request_timeout_sec=data.get("request_timeout_sec", 60),
        )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"type": self.type}
        if self.command:
            d["command"] = self.command
        if self.args:
            d["args"] = self.args
        if self.env:
            d["env"] = self.env
        if self.url:
            d["url"] = self.url
        if self.headers:
            d["headers"] = self.headers
        return d


# --------------------------------------------------------------------------- #
#  MCP 连接抽象
# --------------------------------------------------------------------------- #


class MCPConnection:
    """单个 MCP Server 连接的抽象（v6.0：官方 MCP SDK 客户端，三 transport）。

    - streamable-http（type=http）：``streamablehttp_client``（2025-03-26）
    - stdio：``stdio_client``（子进程 + stdin/stdout）
    - sse：``sse_client``（2024-11-05 经典 SSE）
    SDK 自动完成 initialize/版本协商；连接生命周期由 AsyncExitStack 管理。
    """

    def __init__(self, server_name: str, config: MCPServerConfig) -> None:
        self.server_name = server_name
        self.config = config
        self._initialized = False
        self._tools: Optional[List[Dict[str, Any]]] = None
        self._stack = None
        self._session = None

    async def connect(self) -> None:
        """建立连接（SDK 客户端 + ClientSession + initialize）。"""
        if self._initialized:
            return
        from contextlib import AsyncExitStack

        from mcp import ClientSession
        from mcp.client.sse import sse_client
        from mcp.client.stdio import stdio_client
        from mcp.client.streamable_http import streamablehttp_client

        logger.info(
            "[MCP Client] Connecting to '%s' (type=%s)",
            self.server_name,
            self.config.type,
        )
        cfg = self.config
        if cfg.type == "http":
            if not cfg.url:
                raise ValueError(f"MCP Server '{self.server_name}' http 类型需配置 url")
            ctx = streamablehttp_client(cfg.url, headers=cfg.headers)
        elif cfg.type == "stdio":
            if not cfg.command:
                raise ValueError(
                    f"MCP Server '{self.server_name}' stdio 类型需配置 command"
                )
            from mcp.client.stdio import StdioServerParameters

            server_params = StdioServerParameters(
                command=cfg.command,
                args=cfg.args or [],
                env=cfg.env,
            )
            ctx = stdio_client(server_params)
        elif cfg.type == "sse":
            if not cfg.url:
                raise ValueError(f"MCP Server '{self.server_name}' sse 类型需配置 url")
            ctx = sse_client(cfg.url, headers=cfg.headers)
        else:
            raise ValueError(f"不支持的 transport 类型: {cfg.type}")

        self._stack = AsyncExitStack()
        streams = await self._stack.enter_async_context(ctx)
        # stdio 返回 (read, write)；streamable-http/sse 返回
        # (read, write, get_session_id)
        read, write = streams[0], streams[1]
        self._session = await self._stack.enter_async_context(
            ClientSession(read, write)
        )
        await self._session.initialize()
        self._initialized = True

    async def disconnect(self) -> None:
        """释放连接资源。"""
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None
        self._initialized = False
        self._tools = None

    async def list_tools(self) -> List[Dict[str, Any]]:
        """列出远端 MCP Server 暴露的所有工具（SDK tools/list）。"""
        if self._tools is not None:
            return self._tools
        if self._session is None:
            await self.connect()
        tools_result = await self._session.list_tools()
        self._tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": getattr(t, "inputSchema", None) or {},
            }
            for t in tools_result.tools
        ]
        return self._tools

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用远端工具（SDK tools/call）。"""
        if self._session is None:
            await self.connect()
        result = await self._session.call_tool(tool_name, arguments or {})
        text_parts = [c.text for c in result.content if getattr(c, "text", None)]
        text = "\n".join(text_parts)
        if result.isError:
            return {"error": {"code": -32002, "message": text or f"tool error: {tool_name}"}}
        return {"content": text}


# --------------------------------------------------------------------------- #
#  连接管理器（参照 Proma PiMcpClientManager）
# --------------------------------------------------------------------------- #


def _config_hash(config: MCPServerConfig) -> str:
    """稳定 hash：保证相同配置产生相同 key（排序 key）。"""
    canonical = json.dumps(config.to_dict(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _normalize_tool_segment(segment: str) -> str:
    """将 MCP 工具/服务器名归一化为合法 Python 标识符。

    参照 Proma 的 normalizeToolSegment：
    - 非字母数字字符替换为 _
    - 连续下划线合并
    - 首字符非字母/下划线时加前缀 _
    """
    import re
    normalized = re.sub(r"[^A-Za-z0-9_]", "_", segment)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        return "unnamed"
    if not normalized[0].isalpha() and normalized[0] != "_":
        return f"_{normalized}"
    return normalized


def mcp_tool_name(server_name: str, tool_name: str) -> str:
    """生成 DDW 风格的 MCP 工具名：``ddw.mcp__{server}__{tool}``。

    参照 Proma 的 ``mcp__{serverName}__{toolName}`` 格式，
    加 ``ddw.`` 前缀以统一到 DDW 工具命名空间。
    """
    return f"ddw.mcp__{_normalize_tool_segment(server_name)}__{_normalize_tool_segment(tool_name)}"


class MCPClientManager:
    """MCP Client 连接管理器（单例模式）。

    管理所有外部 MCP Server 的连接，支持：
    - 连接缓存（相同配置复用连接）
    - 配置变更自动重连（config hash 检测）
    - 批量列出所有已连接 server 的 tools
    - 资源释放

    使用::

        manager = MCPClientManager()
        manager.configure("knowledge-server", {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@example/knowledge-mcp"]
        })
        tools = await manager.list_all_tools()
        result = await manager.call_tool("knowledge-server", "search", {"query": "SPC"})
    """

    def __init__(self) -> None:
        self._connections: Dict[str, MCPConnection] = {}
        self._configs: Dict[str, MCPServerConfig] = {}

    def configure(self, server_name: str, config_dict: Dict[str, Any]) -> None:
        """配置一个 MCP Server（不立即连接）。"""
        config = MCPServerConfig.from_dict(config_dict)
        self._configs[server_name] = config
        logger.info("[MCP Client] Configured '%s' (type=%s)", server_name, config.type)

    def configure_many(self, servers: Dict[str, Dict[str, Any]]) -> None:
        """批量配置 MCP Server。"""
        for name, cfg_dict in servers.items():
            self.configure(name, cfg_dict)

    def remove(self, server_name: str) -> None:
        """移除配置（不影响已有连接）。"""
        self._configs.pop(server_name, None)

    async def _get_connection(self, server_name: str) -> MCPConnection:
        """获取连接（缓存优先，配置变更时自动重连）。"""
        config = self._configs.get(server_name)
        if config is None:
            raise ValueError(f"MCP Server '{server_name}' not configured")

        existing = self._connections.get(server_name)
        if existing is not None:
            return existing

        conn = MCPConnection(server_name, config)
        await conn.connect()
        self._connections[server_name] = conn
        return conn

    async def list_tools(self, server_name: str) -> List[Dict[str, Any]]:
        """列出指定 MCP Server 的所有工具。"""
        conn = await self._get_connection(server_name)
        return await conn.list_tools()

    async def list_all_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """列出所有已配置 MCP Server 的工具。"""
        result: Dict[str, List[Dict[str, Any]]] = {}
        for name in self._configs:
            try:
                result[name] = await self.list_tools(name)
            except Exception as e:
                logger.error("[MCP Client] Failed to list tools for '%s': %s", name, e)
                result[name] = []
        return result

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """调用指定 MCP Server 的指定工具。"""
        conn = await self._get_connection(server_name)
        return await conn.call_tool(tool_name, arguments)

    async def dispose(self) -> None:
        """释放所有连接。应在应用退出时调用。"""
        for name, conn in self._connections.items():
            try:
                await conn.disconnect()
            except Exception:
                logger.warning("[MCP Client] Error disconnecting '%s'", name, exc_info=True)
        self._connections.clear()

    @property
    def configured_servers(self) -> List[str]:
        """返回所有已配置的 server 名称。"""
        return list(self._configs.keys())


# 全局单例
_manager: Optional[MCPClientManager] = None


def get_mcp_client() -> MCPClientManager:
    """获取全局 MCP Client Manager 单例。"""
    global _manager
    if _manager is None:
        _manager = MCPClientManager()
    return _manager


__all__ = [
    "MCPServerConfig",
    "MCPConnection",
    "MCPClientManager",
    "get_mcp_client",
    "mcp_tool_name",
]
