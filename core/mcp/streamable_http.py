"""DDW MCP streamable-http 兼容层（v6.0，路线乙：官方 MCP Python SDK）。

- 用官方 ``FastMCP`` 承载双协议（2024-11-05 + 2025-03-26）——SDK 自动版本协商；
- 把 DDW 现有 ``ToolRegistry`` / ``ResourceRegistry`` 的工具与资源注册进 FastMCP；
- ``streamable_http_app()`` 返回 Starlette 应用，挂载到 FastAPI
  ``POST/GET /api/v1/mcp``；
- 会话管理（Mcp-Session-Id / TTL 回收 / 无会话非 initialize → 400）由 SDK
  ``StreamableHTTPServerTransport`` 处理（规范 §3.4）。

经典端点（/api/v1/mcp/jsonrpc|sse|info）保持手写实现不动（双轨并存）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# 延迟创建单例（避免 import 时拉起工具注册/依赖）
_fastmcp = None


def _build_wrapped(handler, parameters: Dict[str, Any]):
    """按 DDW 工具 JSON Schema 生成扁平参数签名的异步包装函数。

    FastMCP 根据函数签名生成 tools/list 的 inputSchema，所以包装函数必须
    把 DDW 工具的 properties/required 展开为真实参数（含类型注解），而不是
    收一个 ``arguments: dict``——后者会让客户端被迫传嵌套参数。
    enum 通过 Literal 表达；可选参数默认 None。
    """
    from typing import Any, Literal, Optional

    props = (parameters or {}).get("properties", {})
    required = set((parameters or {}).get("required", []))
    parts = []
    for name, ps in props.items():
        t = ps.get("type")
        type_map = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
        }
        ann = type_map.get(t, "Any")
        if ps.get("enum"):
            choices = ", ".join(repr(c) for c in ps["enum"])
            ann = f"Literal[{choices}]"
        if name not in required:
            ann = f"Optional[{ann}]"
        default = "" if name in required else " = None"
        parts.append(f"{name}: {ann}{default}")

    signature = ", ".join(parts) or "*args"
    if parts:
        body = "return await _handler(locals(), {})"
    else:
        body = "return await _handler(dict(args or ()), {})"
    src = f"async def _wrapped({signature}):\n    {body}\n"
    ns: Dict[str, Any] = {
        "_handler": handler,
        "Any": Any,
        "Optional": Optional,
        "Literal": Literal,
    }
    exec(src, ns)  # noqa: S102  # 仅由本模块受控的 schema 生成
    return ns["_wrapped"]


def _build_fastmcp():
    """构造 FastMCP 实例并把 DDW 现有工具/资源注册进去（幂等）。"""
    from mcp.server.fastmcp import FastMCP

    from core.mcp.protocol import SERVER_INFO
    from core.mcp.server import get_mcp_server

    # 注：mcp 1.29 的 FastMCP 不接收 version 参数，构造后再注入 server_info 版本号。
    # host=0.0.0.0：避免 SDK 对 127.0.0.1 自动启用 DNS 重绑定保护
    # （421 拦截测试/代理 host）。
    mcp = FastMCP(
        name=SERVER_INFO["name"],
        instructions=SERVER_INFO.get("description", ""),
        streamable_http_path="/",  # 挂载到 /api/v1/mcp 后，根路径即端点
        host="0.0.0.0",
    )
    mcp._mcp_server.version = SERVER_INFO["version"]

    core_server = get_mcp_server()

    # 注册工具：把 DDW 工具按自身参数 schema 注册进 FastMCP
    for tool in core_server.tools.list():
        handler = tool.handler
        if handler is None:
            continue
        tool_name = tool.name  # 形如 ddw.llm.chat
        tool_desc = tool.description

        mcp.add_tool(
            _build_wrapped(handler, tool.parameters),
            name=tool_name,
            description=tool_desc,
        )
        logger.info("mcp streamable-http registered tool %s", tool_name)

    return mcp


def get_fastmcp():
    """返回 FastMCP 单例（懒创建）。"""
    global _fastmcp
    if _fastmcp is None:
        _fastmcp = _build_fastmcp()
    return _fastmcp


class _RootPathNormalizer:
    """ASGI 包装：Starlette 的 ``Route("/api/v1/mcp")`` 精确匹配后子应用仍看到
    原始路径 ``/api/v1/mcp``，而 SDK 内部路由是 ``Route("/")``，会 404/307。
    这里把子路径规范化为 ``/``（并保留 root_path 信息）再交给 SDK 应用。

    同时负责 SDK ``StreamableHTTPSessionManager`` 的生命周期：SDK 的
    ``streamable_http_app()`` 在 Starlette lifespan 里 ``async with run()``，
    但以 Route 方式注册时不会触发 Starlette lifespan，因此在首次请求时
    惰性进入 ``run()`` 上下文（幂等，事件循环内常驻 task group）。
    """

    def __init__(self, app, manager):
        self.app = app
        self._manager = manager
        self._exit_stack = None

    async def _ensure_manager(self):
        # run() 只能调用一次：仅当 task group 尚未初始化时惰性进入。
        # 若调用方（如测试 fixture）已 async with manager.run()，这里直接跳过。
        if self._manager._task_group is None and self._exit_stack is None:
            from contextlib import AsyncExitStack

            stack = AsyncExitStack()
            await stack.enter_async_context(self._manager.run())
            self._exit_stack = stack

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            await self._ensure_manager()
            scope["path"] = "/"
            scope["root_path"] = scope.get("root_path", "")
        await self.app(scope, receive, send)


def register_streamable_http(app):
    """把 streamable-http 单端点注册到 FastAPI 应用。

    不使用 ``app.mount``：Mount 的 path_regex 是 ``/api/v1/mcp/{path:path}``，
    无尾斜杠请求（规范端点 URL）会触发 redirect_slashes 307，而 SDK 客户端
    默认不跟随重定向。改用 ``Route`` 精确匹配 ``/api/v1/mcp``。
    """
    from starlette.routing import Route

    fastmcp = get_fastmcp()
    endpoint = _RootPathNormalizer(
        fastmcp.streamable_http_app(),
        fastmcp._session_manager,
    )
    app.router.routes.append(
        Route(
            "/api/v1/mcp",
            endpoint=endpoint,
            methods=["GET", "POST", "DELETE", "OPTIONS"],
            name="mcp-streamable-http",
            include_in_schema=False,
        )
    )


def streamable_http_app():
    """兼容旧调用：返回包装后的 streamable-http Starlette 应用。"""
    fastmcp = get_fastmcp()
    return _RootPathNormalizer(fastmcp.streamable_http_app(), fastmcp._session_manager)


__all__ = ["get_fastmcp", "streamable_http_app", "register_streamable_http"]
