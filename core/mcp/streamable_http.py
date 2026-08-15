"""deepDDW MCP streamable-http 兼容层（v6.0 修复版，开源裁剪）。

- 用官方 ``FastMCP`` 承载双协议（2024-11-05 + 2025-03-26）——SDK 自动版本协商；
- 把 DDW 现有 ``ToolRegistry`` 的工具注册进 FastMCP；
- ``streamable_http_app()`` 返回 Starlette 应用，挂载到 FastAPI
  ``POST/GET /api/v1/mcp``；
- 会话管理（Mcp-Session-Id / TTL 回收 / 无会话非 initialize → 400）由 SDK
  ``StreamableHTTPServerTransport`` 处理（规范 §3.4）。

修复（相对商业仓 6.0）：
- P0-2：FastMCP 工具注册改为**插件加载完成后**执行——``lifespan`` 内
  ``load_plugins()`` 之后调用 ``rebuild_fastmcp()`` 重建单例；
  路由端点请求时才解析 FastMCP，避免 create_app 阶段抓取空工具快照。
- P0-1：路由整体套 ``TokenGateASGI``（Bearer / X-DDW-Token，缺失/无效 → 401）。
- P1-2：``exec`` 动态签名加固——参数名 ``str.isidentifier()`` 校验、
  enum 值 repr 转义、SDK 私有属性访问 try/except 降级。

经典端点（/api/v1/mcp/jsonrpc|sse|info）保持手写实现不动（双轨并存）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# 延迟创建单例（避免 import 时拉起工具注册/依赖）
_fastmcp = None


def _safe_identifier(name: Any) -> bool:
    """参数名必须为合法 Python 标识符（P1-2：非标识符参数名直接拒绝，不 exec）。"""
    return isinstance(name, str) and name.isidentifier() and name not in {"_handler", "args", "kwargs"}


def _build_wrapped(handler, parameters: Dict[str, Any]):
    """按 DDW 工具 JSON Schema 生成扁平参数签名的异步包装函数。

    FastMCP 根据函数签名生成 tools/list 的 inputSchema，所以包装函数必须
    把 DDW 工具的 properties/required 展开为真实参数（含类型注解），而不是
    收一个 ``arguments: dict``——后者会让客户端被迫传嵌套参数。
    enum 通过 Literal 表达；可选参数默认 None。

    加固（P1-2）：
    - 参数名必须 ``str.isidentifier()``，否则跳过该参数（防 exec 注入）；
    - enum 值一律 ``repr()`` 转义后拼进 Literal（防引号注入）；
    - 无合法参数时回退 ``*args`` 收 dict，不拼危险签名。
    """
    from typing import Any, Literal, Optional

    props = (parameters or {}).get("properties", {})
    required = set((parameters or {}).get("required", []))
    parts = []
    for name, ps in props.items():
        if not _safe_identifier(name):
            logger.warning("mcp schema param %r is not a safe identifier, skipped", name)
            continue
        t = ps.get("type")
        type_map = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
        }
        ann = type_map.get(t, "Any")
        if ps.get("enum"):
            # repr 转义 enum 值：任何非法标识符/引号内容都安全落在 Literal 字符串内
            choices = ", ".join(repr(c) for c in ps["enum"])
            ann = f"Literal[{choices}]"
        if name not in required:
            ann = f"Optional[{ann}]"
        default = "" if name in required else " = None"
        parts.append((name, f"{name}: {ann}{default}", name in required))

    # 必填参数必须排在可选参数之前（否则生成非法签名 SyntaxError）
    parts.sort(key=lambda item: (not item[2], item[0]))
    signature = ", ".join(p[1] for p in parts) or "*args"
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
    exec(src, ns)  # noqa: S102  # 参数名已 isidentifier 校验、enum 已 repr 转义
    return ns["_wrapped"]


def _build_fastmcp():
    """构造 FastMCP 实例并把 DDW 现有工具注册进去（幂等，需在插件加载后调用）。"""
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
    # P1-2：SDK 私有属性访问加 try/except 降级（不同 SDK 版本属性名可能不同）
    try:
        mcp._mcp_server.version = SERVER_INFO["version"]  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        logger.debug("mcp _mcp_server.version set skipped: %s", exc)

    core_server = get_mcp_server()

    # 注册工具：把 DDW 白名单工具按自身参数 schema 注册进 FastMCP
    # （与经典端点 tools/list 同源：public_tools() 做 license 分层过滤）
    for tool in core_server.public_tools():
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


def rebuild_fastmcp():
    """P0-2：丢弃旧 FastMCP 单例并重建。

    必须在 ``load_plugins()`` 之后调用——此时插件已把 override 工具注册进
    ``ToolRegistry``，重建后的 FastMCP 工具快照与经典端点 tools/list 一致。
    """
    global _fastmcp
    _fastmcp = None
    logger.info("mcp streamable-http: rebuilding FastMCP after plugin load")
    return get_fastmcp()


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

    生命周期说明（P0-2）：SDK ``StreamableHTTPSessionManager`` 由
    ``core.main.lifespan`` 显式 ``async with run()`` 常驻；本包装仅当
    task group 尚未初始化时（如独立测试进程）惰性进入，幂等。
    """

    def __init__(self, app, manager):
        self.app = app
        self._manager = manager
        self._exit_stack = None

    async def _ensure_manager(self):
        # run() 只能调用一次：仅当 task group 尚未初始化时惰性进入。
        # 若调用方（如 lifespan / 测试 fixture）已 async with manager.run()，这里直接跳过。
        try:
            if self._manager._task_group is None and self._exit_stack is None:  # type: ignore[attr-defined]
                from contextlib import AsyncExitStack

                stack = AsyncExitStack()
                await stack.enter_async_context(self._manager.run())
                self._exit_stack = stack
        except Exception as exc:  # noqa: BLE001  # P1-2：SDK 私有属性降级
            logger.debug("mcp session manager lazy-run skipped: %s", exc)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            await self._ensure_manager()
            scope["path"] = "/"
            scope["root_path"] = scope.get("root_path", "")
        await self.app(scope, receive, send)


class _LazyMCPApp:
    """请求时才解析 FastMCP 单例（P0-2 关键）。

    ``register_streamable_http`` 在 create_app（模块级）执行时**不**抓工具快照；
    首次请求发生在 lifespan 完成（load_plugins → rebuild_fastmcp）之后，
    因此这里拿到的必为插件加载后的工具集合。

    rebuild 感知：若 ``get_fastmcp()`` 已被 ``rebuild_fastmcp()`` 替换为新的
    单例（对象身份变化），请求时自动重建底层 normalizer，保证永远服务最新
    工具快照（测试中多次 rebuild 的场景同样成立）。
    """

    def __init__(self) -> None:
        self._fastmcp = None
        self._normalizer = None

    async def __call__(self, scope, receive, send):
        fastmcp = get_fastmcp()
        if self._normalizer is None or fastmcp is not self._fastmcp:
            # 注意：fastmcp._session_manager 在 streamable_http_app() 首次调用前为 None，
            # 必须先构建应用再取 manager（P1-2：私有属性访问 try/except 降级）。
            sdk_app = fastmcp.streamable_http_app()
            manager = None
            try:
                manager = fastmcp._session_manager  # type: ignore[attr-defined]
            except Exception as exc:  # noqa: BLE001
                logger.debug("mcp _session_manager access skipped: %s", exc)
            self._fastmcp = fastmcp
            self._normalizer = _RootPathNormalizer(sdk_app, manager)
        await self._normalizer(scope, receive, send)


def register_streamable_http(app):
    """把 streamable-http 单端点注册到 FastAPI 应用（带 Token 门禁）。

    不使用 ``app.mount``：Mount 的 path_regex 是 ``/api/v1/mcp/{path:path}``，
    无尾斜杠请求（规范端点 URL）会触发 redirect_slashes 307，而 SDK 客户端
    默认不跟随重定向。改用 ``Route`` 精确匹配 ``/api/v1/mcp``。
    """
    from starlette.routing import Route

    from core.security.token_gate import TokenGateASGI

    endpoint = TokenGateASGI(_LazyMCPApp())
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
    """兼容旧调用：返回包装后的 streamable-http Starlette 应用（不套门禁，供测试）。"""
    fastmcp = get_fastmcp()
    manager = None
    try:
        manager = fastmcp._session_manager  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001
        logger.debug("mcp _session_manager access skipped: %s", exc)
    return _RootPathNormalizer(fastmcp.streamable_http_app(), manager)


__all__ = [
    "get_fastmcp",
    "rebuild_fastmcp",
    "streamable_http_app",
    "register_streamable_http",
    "_build_wrapped",
]
