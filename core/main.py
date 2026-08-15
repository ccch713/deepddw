"""DDW AI Hub FastAPI 应用入口（v5.4）。

启动：
    cd /Users/chenye/workspace/ddw-ai-hub
    python -m uvicorn core.main:app --host 0.0.0.0 --port 8500

注意：
- lifespan 中初始化 DB schema、注册 tenant hooks、加载插件
- CORS 开启（dev 默认全开，生产应收紧）
- 静态 HTML 页面由 :class:`StaticFiles` 挂载在 ``/`` 上
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from core.api.admin import router as admin_router
from core.api.auth import router as auth_router
from core.api.chat import router as chat_router
from core.api.docs import router as docs_router
from core.api.forum import router as forum_router
from core.api.knowledge import router as knowledge_router
from core.api.llm import router as llm_router
from core.api.license import router as license_router
from core.api.skills import router as skills_router
from core.api.sso import router as sso_router
from core.api.user import router as user_router
from core.api.users import router as users_router
from core.config import get_settings
from core.database.session import dispose_db, get_engine, init_db
from core.database.tenant_filter import install_tenant_hooks
from core.mcp.protocol import SERVER_CAPABILITIES, SERVER_INFO
from core.mcp.server import get_mcp_server
from core.middleware.tenant import TenantContextMiddleware

# 版本唯一来源：仓库根 VERSION 文件（FastAPI 元信息 / /health / /api/v1/version 统一读取）
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
    """扫描 ``plugins/*/manifest.yaml``，通过 PluginBase 注册 router（P4 热加载运行时）。

    - 授权门控（license 验签/fail-closed/DDW_ENV 加固）由
      ``core.plugin_manager.runtime.resolve_license_gate`` 统一解析（P3 语义保留）
    - 加载逻辑走 ``PluginRuntime``（启动批量加载；同一运行时供热装/停用/重挂复用）
    - 运行时挂到 ``app.state.plugin_runtime``（供管理端点热插拔调用）
    """
    settings = get_settings()
    plugin_root = settings.plugin_root

    # 动态 import 每个插件的 ``plugin.py``
    import sys

    # 确保 plugins/ 目录在 sys.path 中（供 embedded_llm 等内部模块导入）
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
    logger.info("DDW AI Hub starting… mode=%s", get_settings().mode)
    engine = get_engine()
    install_tenant_hooks(engine)
    # 先加载插件（注册模型到 Base.metadata），再建表
    plugins = load_plugins(app)
    app.state.plugins = plugins
    await init_db()
    # SQLAdmin 挂载 /admin（密码认证见 core/admin/__init__.py）
    from core.admin import setup_admin

    app.state.sql_admin = setup_admin(app, engine)
    logger.info("DDW AI Hub started, %d plugins loaded", len(plugins))
    # MCP streamable-http：SDK session manager 必须在 lifespan 中常驻
    # （惰性在请求内启动会与 BaseHTTPMiddleware 的 task group 冲突）
    from core.mcp.streamable_http import get_fastmcp

    try:
        mcp_manager = get_fastmcp()._session_manager
    except Exception as e:  # noqa: BLE001
        mcp_manager = None
        logger.warning("mcp streamable-http session manager 初始化失败: %s", e)
    try:
        if mcp_manager is not None:
            async with mcp_manager.run():
                yield
        else:
            yield
    finally:
        await dispose_db()
        logger.info("DDW AI Hub stopped")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    app = FastAPI(
        title="DDW AI Hub",
        version=APP_VERSION,
        description="DDW AI Hub — 渡笃微 AI 底座平台",
        lifespan=lifespan,
    )

    # CORS（白名单；生产域 + 本地开发域）
    # 注意：allow_credentials=True 时不能用 "*"
    cors_origins = [
        "https://ddw.9cio.com",
        "https://www.9cio.com",
        "https://wenquedu.com",
        "http://localhost:8500",
        "http://localhost:3000",
        "http://localhost:8766",
        "http://127.0.0.1:8500",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8766",
    ]
    # 泛微OA域名（SSO回调需要）
    weaver_oa_url = os.environ.get("DDW_WEAVER_OA_URL", "")
    if weaver_oa_url:
        cors_origins.append(weaver_oa_url.rstrip("/"))
    # 可通过环境变量追加（如预发/灰度）
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
    # 租户上下文中间件（在 CORS 之后注册，先执行）
    app.add_middleware(TenantContextMiddleware)
    # SQLAdmin 认证用 Session（secret 复用 JWT 密钥）
    from starlette.middleware.sessions import SessionMiddleware

    app.add_middleware(
        SessionMiddleware,
        secret_key=os.environ.get("DDW_JWT_SECRET", "ddw-dev-secret"),
        max_age=60 * 60 * 8,  # 8 小时
    )

    # API 路由
    app.include_router(auth_router)
    app.include_router(admin_router)
    app.include_router(license_router)
    app.include_router(docs_router)
    app.include_router(forum_router)
    app.include_router(knowledge_router)
    app.include_router(user_router)
    app.include_router(users_router)
    app.include_router(llm_router)
    app.include_router(sso_router)  # 泛微OA SSO
    app.include_router(chat_router)  # DDW Pal 对话（2026-08-11 挂载）
    app.include_router(skills_router)  # DDW Pal Skill 创建（2026-08-11 挂载）

    # 健康检查
    @app.get("/health")
    async def health() -> Dict[str, Any]:
        return {"status": "ok", "service": "ddw-ai-hub", "version": APP_VERSION}

    @app.get("/api/v1/version")
    async def version() -> Dict[str, Any]:
        s = get_settings()
        return {
            "version": APP_VERSION,
            "mode": s.mode,
            "plugins_root": str(s.plugin_root),
            "llm_provider": s.llm.get("default_provider", "minimax"),
        }

    # ---- MCP（模块 D2） ----
    @app.get("/api/v1/mcp/info")
    async def mcp_info() -> Dict[str, Any]:
        return {"serverInfo": SERVER_INFO, "capabilities": SERVER_CAPABILITIES}

    @app.post("/api/v1/mcp/jsonrpc")
    async def mcp_jsonrpc(payload: Dict[str, Any]) -> Dict[str, Any]:
        mcp = get_mcp_server()
        result = await mcp.handle_request(payload, context={"request": "http"})
        # 通知（无 id）返回 204
        if result is None:
            from fastapi import Response
            return Response(status_code=204)
        return result

    @app.get("/api/v1/mcp/sse")
    async def mcp_sse():
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

    # ---- MCP streamable-http（v6.0 双协议，单端点 POST/GET /api/v1/mcp）----
    # 会话管理（Mcp-Session-Id）/ Accept 协商 / 版本协商由官方 SDK 处理；
    # 经典端点 /api/v1/mcp/jsonrpc|sse|info 保持不动（双轨并存）。
    try:
        from core.mcp.streamable_http import register_streamable_http

        register_streamable_http(app)
    except Exception as e:  # noqa: BLE001  # SDK 缺失/初始化失败不阻塞启动
        logger.warning("mcp streamable-http 挂载失败（跳过）: %s", e)

    # 静态前端（saas-*.html, ddw-*.html）
    frontend = Path(__file__).resolve().parent.parent / "frontend"
    if frontend.exists():
        app.mount("/ui", StaticFiles(directory=str(frontend), html=True), name="frontend")
        # 根路径重定向到欢迎页
        @app.get("/", include_in_schema=False)
        async def root():
            return RedirectResponse(url="/ui/welcome.html")
    else:
        logger.warning("frontend directory not found: %s", frontend)

    return app


app = create_app()


__all__ = ["app", "create_app", "load_plugins"]
