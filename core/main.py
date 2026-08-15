"""deepDDW FastAPI 应用入口（开源裁剪版 0.1）。

启动：
    python -m uvicorn core.main:app --host 0.0.0.0 --port 8500

注意：
- lifespan 中加载白名单插件（load_plugins）→ **重建 FastMCP**（P0-2：
  工具注册必须在插件加载完成后执行）→ 常驻 MCP session manager；
- 全局网关 Token 门禁（P0-1）：MCP 全部端点（streamable-http + 经典）与
  网关 API 必须携带 ``Authorization: Bearer <token>`` 或 ``X-DDW-Token``，
  缺失/无效 → 401；
- 无账号体系（无 JWT / 无租户 / 无 admin 后台）；静态 HTML 由 StaticFiles 挂载。
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from core.api.chat import router as chat_router
from core.api.knowledge import router as knowledge_router
from core.api.llm import router as llm_router
from core.config import get_settings
from core.database.session import dispose_db, init_db
from core.mcp.protocol import SERVER_CAPABILITIES, SERVER_INFO
from core.mcp.server import get_mcp_server
from core.security.token_gate import lan_bypass_enabled, require_access_token

# 版本唯一来源：仓库根 VERSION 文件
_APP_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"
try:
    APP_VERSION = _APP_VERSION_FILE.read_text(encoding="utf-8").strip()
except OSError:
    APP_VERSION = "0.0.0-dev"

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=os.environ.get("DDW_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


# ---------------------------------------------------------------------------
# 插件加载
# ---------------------------------------------------------------------------


def load_plugins(app: FastAPI) -> Dict[str, Any]:
    """扫描 ``plugins/*/manifest.yaml``，通过 PluginBase 注册 router。

    deepDDW 插件目录只含白名单组件（ddw-docs-portal / ddw-searxng）；
    无 license 授权门控（开源版恒放行）。
    """
    settings = get_settings()
    plugin_root = settings.plugin_root

    import sys

    # 确保 plugins/ 目录在 sys.path 中（供插件内部模块导入）
    plugins_dir_str = str(plugin_root)
    if plugins_dir_str not in sys.path:
        sys.path.insert(0, plugins_dir_str)

    from core.plugin_manager.runtime import PluginRuntime

    runtime = PluginRuntime(app=app, plugin_root=plugin_root, settings=settings)
    app.state.plugin_runtime = runtime
    return runtime.load_many()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # P2-3：启动期 fail-fast——未配置访问 Token 直接拒绝启动
    # （绝不以公开默认值运行；门禁形同虚设比不启动更危险）。
    from core.security.token_gate import get_access_token

    get_access_token()
    logger.info("deepDDW starting… mode=%s", get_settings().mode)
    # 先加载插件（注册模型到 Base.metadata），再建表
    plugins = load_plugins(app)
    app.state.plugins = plugins
    await init_db()
    logger.info("deepDDW started, %d plugins loaded", len(plugins))

    # P0-2：FastMCP 工具注册必须在插件加载完成后执行——
    # lifespan 内 load_plugins() 之后重建 FastMCP（工具快照含插件 override 工具）。
    from core.mcp.streamable_http import rebuild_fastmcp

    try:
        fastmcp = rebuild_fastmcp()
        # 先构建 SDK 应用（初始化 session manager），再取 manager 常驻（P1-2 降级）
        fastmcp.streamable_http_app()
        manager = None
        try:
            manager = fastmcp._session_manager  # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001  # P1-2：SDK 私有属性降级
            logger.warning("mcp _session_manager access failed: %s", e)
        if manager is not None:
            # SDK session manager 必须在 lifespan 中常驻
            # （惰性在请求内启动会与 BaseHTTPMiddleware 的 task group 冲突）
            async with manager.run():
                yield
        else:
            yield
    finally:
        await dispose_db()
        logger.info("deepDDW stopped")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(
        title="deepDDW",
        version=APP_VERSION,
        description="deepDDW — 开源个人 AI 底座（DSH + 知识库 + 记忆 + 网关 + MCP）",
        lifespan=lifespan,
    )

    # CORS（本地开发域；生产由反向代理收敛）
    cors_origins = [
        "http://localhost:8500",
        "http://localhost:3000",
        "http://localhost:8766",
        "http://127.0.0.1:8500",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8766",
    ]
    extra = os.environ.get("DDW_CORS_EXTRA_ORIGINS", "")
    if extra:
        cors_origins += [o.strip() for o in extra.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API 路由（全部走网关 Token 门禁；无账号体系）
    app.include_router(chat_router)
    app.include_router(knowledge_router)
    app.include_router(llm_router)

    # 健康检查（公开）
    @app.get("/health")
    async def health() -> Dict[str, Any]:
        return {"status": "ok", "service": "deepddw", "version": APP_VERSION}

    # 网关信息（公开；PWA 启动页据此探测地址可达性）
    @app.get("/api/v1/version")
    async def version() -> Dict[str, Any]:
        s = get_settings()
        return {
            "version": APP_VERSION,
            "mode": s.mode,
            "plugins_root": str(s.plugin_root),
            "llm_provider": s.llm.get("default_provider", "deepseek"),
            "auth": "token",
        }

    # P0-1 第 4 条：PWA 启动页 Token 校验端点（Bearer / X-DDW-Token，无效 → 401）
    @app.get("/api/v1/gateway/verify")
    async def gateway_verify(claims: Dict[str, Any] = Depends(require_access_token)) -> Dict[str, Any]:
        return {
            "ok": True,
            "service": "deepddw",
            "version": APP_VERSION,
            "authenticated": True,
            "token_valid": True,
        }

    # 体验优化 C：扫码配对端点——返回"带 Token 的启动 URL"及二维码 SVG。
    # 仅 LAN 或已授权可调；启动页显示二维码，手机扫码自动预填 Token。
    @app.get("/api/v1/gateway/pair")
    async def gateway_pair(
        request: Request, claims: Dict[str, Any] = Depends(require_access_token)
    ) -> Dict[str, Any]:
        from core.security.token_gate import get_access_token

        token = get_access_token()
        # 构造扫码 URL：优先用请求 Host（含端口），确保手机可访问
        host = request.headers.get("x-forwarded-host") or request.headers.get(
            "host"
        ) or "localhost"
        scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
        pair_url = f"{scheme}://{host}/?token={token}"
        qr_svg = ""
        try:
            import io

            import qrcode
            from qrcode.image.svg import SvgPathImage

            qr = qrcode.QRCode(border=1, box_size=8)
            qr.add_data(pair_url)
            qr.make(fit=True)
            img = qr.make_image(image_factory=SvgPathImage)
            buf = io.BytesIO()
            img.save(buf)
            qr_svg = buf.getvalue().decode("utf-8")
        except Exception as exc:  # noqa: BLE001  # 二维码不可用不影响主流程
            logger.warning("pair qr generation failed: %s", exc)
        return {
            "ok": True,
            "pair_url": pair_url,
            "qr_svg": qr_svg,
            "lan_bypass": lan_bypass_enabled(),
            "hint": "手机扫码打开此链接即自动填入 Token",
        }

    # ---- MCP（经典端点 + streamable-http，全部过 Token 门禁）----
    @app.get("/api/v1/mcp/info")
    async def mcp_info(claims: Dict[str, Any] = Depends(require_access_token)) -> Dict[str, Any]:
        return {"serverInfo": SERVER_INFO, "capabilities": SERVER_CAPABILITIES}

    @app.post("/api/v1/mcp/jsonrpc")
    async def mcp_jsonrpc(payload: Dict[str, Any], claims: Dict[str, Any] = Depends(require_access_token)) -> Dict[str, Any]:
        mcp = get_mcp_server()
        result = await mcp.handle_request(payload, context={"request": "http"})
        # 通知（无 id）返回 204
        if result is None:
            from fastapi import Response
            return Response(status_code=204)
        return result

    @app.get("/api/v1/mcp/sse")
    async def mcp_sse(claims: Dict[str, Any] = Depends(require_access_token)):
        from fastapi.responses import StreamingResponse

        async def event_stream():
            # 简化：连接时推送 server info，断开时停止
            import asyncio
            import json
            yield f"data: {json.dumps({'event': 'hello', 'server': SERVER_INFO['name']}, ensure_ascii=False)}\n\n"
            while True:
                await asyncio.sleep(15)
                yield ": keep-alive\n\n"
        return StreamingResponse(event_stream(), media_type="text/event-stream")

    # ---- MCP streamable-http（单端点 POST/GET /api/v1/mcp，TokenGateASGI 门禁）----
    # 会话管理（Mcp-Session-Id）/ Accept 协商 / 版本协商由官方 SDK 处理；
    # 工具注册在 lifespan 内 load_plugins 之后重建（P0-2）。
    try:
        from core.mcp.streamable_http import register_streamable_http

        register_streamable_http(app)
    except Exception as e:  # noqa: BLE001  # SDK 缺失/初始化失败不阻塞启动
        logger.warning("mcp streamable-http 挂载失败（跳过）: %s", e)

    # 静态前端（deepddw-launcher / welcome / docs）
    frontend = Path(__file__).resolve().parent.parent / "frontend"
    if frontend.exists():
        app.mount("/ui", StaticFiles(directory=str(frontend), html=True), name="frontend")

        @app.get("/", include_in_schema=False)
        async def root():
            return RedirectResponse(url="/ui/deepddw-launcher.html")
    else:
        logger.warning("frontend directory not found: %s", frontend)

    return app


app = create_app()


__all__ = ["app", "create_app", "load_plugins"]
