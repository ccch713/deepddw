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
from typing import Any, Dict, Optional

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket
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
        # P1-14：关闭 LLM 网关底层 httpx client（防 fd 泄漏）
        try:
            from core.llm_gateway.gateway import aclose_all

            await aclose_all()
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm gateway aclose failed: %s", exc)
        proxy_client = getattr(app.state, "ddw_proxy_client", None)
        if proxy_client is not None:
            try:
                await proxy_client.aclose()
            except Exception as exc:  # noqa: BLE001
                logger.warning("ddw proxy client aclose failed: %s", exc)
        await dispose_db()
        logger.info("deepDDW stopped")


# ---------------------------------------------------------------------------
# 扫码配对一次性码（P0-2：QR 只带 code，不裸拼长期 Token）
# ---------------------------------------------------------------------------

_PAIR_TTL_SECONDS = 60
_PAIR_MAX_ENTRIES = 128
_pair_codes: Dict[str, Dict[str, Any]] = {}


def _issue_pair_code(token: str) -> str:
    """签发 60 秒一次性配对码（带过期时间；超过上限时惰性清理最旧项）。"""
    import secrets
    import time

    now = time.time()
    # 惰性清理过期项 + 上限保护（防内存膨胀）
    expired = [k for k, v in _pair_codes.items() if v.get("expires", 0) <= now]
    for k in expired:
        _pair_codes.pop(k, None)
    if len(_pair_codes) >= _PAIR_MAX_ENTRIES:
        oldest = min(_pair_codes, key=lambda k: _pair_codes[k].get("expires", 0))
        _pair_codes.pop(oldest, None)
    code = secrets.token_urlsafe(16)
    _pair_codes[code] = {"token": token, "expires": now + _PAIR_TTL_SECONDS}
    return code


def _redeem_pair_code(code: str) -> Optional[str]:
    """兑换配对码：有效返回 token 并立即作废；无效返回 None。"""
    import time

    entry = _pair_codes.pop(code, None)
    if entry is None:
        return None
    if entry.get("expires", 0) <= time.time():
        return None
    return entry.get("token")


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

    # P1-17：CORS 从配置读取（deployment.yaml cors.origins > env DDW_CORS_ORIGINS
    # > 本地默认）；allow_headers 收窄到实际使用的头（防任意自定义头跨域携带）。
    _DEFAULT_CORS_ORIGINS = [
        "http://localhost:8500", "http://localhost:3000", "http://localhost:3080",
        "http://localhost:8766",
        "http://127.0.0.1:8500", "http://127.0.0.1:3000", "http://127.0.0.1:3080",
        "http://127.0.0.1:8766",
    ]
    try:
        configured = get_settings().raw.get("cors", {}).get("origins", []) or []
    except Exception:  # noqa: BLE001
        configured = []
    env_origins = os.environ.get("DDW_CORS_ORIGINS", "")
    if env_origins:
        configured = [o.strip() for o in env_origins.split(",") if o.strip()]
    cors_origins = configured or _DEFAULT_CORS_ORIGINS
    extra = os.environ.get("DDW_CORS_EXTRA_ORIGINS", "")
    if extra:
        cors_origins += [o.strip() for o in extra.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
        allow_headers=["Authorization", "X-DDW-Token", "Content-Type", "Mcp-Session-Id"],
    )

    # P0-2（multidevice）：网关限流与过载保护（Token/IP 双维度 + 全局 503）。
    # 配置：deployment.yaml security.rate_limit.* / env DDW_RATE_LIMIT_*。
    try:
        from core.middleware.rate_limit import RateLimitMiddleware

        app.add_middleware(RateLimitMiddleware)
    except Exception as exc:  # noqa: BLE001  # 限流加载失败不阻断启动（降级）
        logger.warning("rate limit middleware disabled: %s", exc)

    # API 路由（全部走网关 Token 门禁；无账号体系）
    app.include_router(chat_router)
    app.include_router(knowledge_router)
    app.include_router(llm_router)
    # P0-3/P0-4（multidevice）：设备注册/心跳 + 状态面板
    from core.api.status import router as status_router

    app.include_router(status_router)
    # P1-1（multidevice）：工作区会话绑定
    from core.api.workspace import router as workspace_router

    app.include_router(workspace_router)

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
    async def gateway_verify(
        claims: Dict[str, Any] = Depends(require_access_token),
    ) -> Dict[str, Any]:
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
        """扫码配对：签发 60 秒一次性配对码，QR/URL 只带 code（不裸拼长期 Token）。

        手机扫码打开 ``?pair_code=<code>`` → launcher 调
        ``/api/v1/gateway/exchange`` 兑换 Token 并自动填入。
        """
        from core.security.token_gate import get_access_token

        token = get_access_token()
        code = _issue_pair_code(token)
        # 构造扫码 URL：优先用请求 Host（含端口），确保手机可访问
        host = request.headers.get("x-forwarded-host") or request.headers.get(
            "host"
        ) or "localhost"
        scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
        pair_url = f"{scheme}://{host}/?pair_code={code}"
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
            "hint": "手机扫码打开此链接即自动填入 Token（一次性，60 秒有效）",
        }

    @app.get("/api/v1/gateway/exchange")
    async def gateway_exchange(
        code: str = Query(..., min_length=8, max_length=64),
    ) -> Dict[str, Any]:
        """兑换一次性配对码 → Token（成功即作废；失败 401，不泄露原因）。"""
        token = _redeem_pair_code(code)
        if token is None:
            raise HTTPException(
                status_code=401, detail="配对码无效或已过期"
            )
        return {"ok": True, "token": token}

    # ---- MCP（经典端点 + streamable-http，全部过 Token 门禁）----
    @app.get("/api/v1/mcp/info")
    async def mcp_info(
        claims: Dict[str, Any] = Depends(require_access_token),
    ) -> Dict[str, Any]:
        return {"serverInfo": SERVER_INFO, "capabilities": SERVER_CAPABILITIES}

    @app.post("/api/v1/mcp/jsonrpc")
    async def mcp_jsonrpc(
        payload: Dict[str, Any],
        claims: Dict[str, Any] = Depends(require_access_token),
    ) -> Dict[str, Any]:
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
            yield (
                "data: " + json.dumps(
                    {"event": "hello", "server": SERVER_INFO["name"]},
                    ensure_ascii=False,
                ) + "\n\n"
            )
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
        app.mount(
            "/ui", StaticFiles(directory=str(frontend), html=True), name="frontend"
        )

        @app.get("/", include_in_schema=False)
        async def root(request: Request):
            # 体验优化 A2（2026-08-16 竞品抢生态位提速）：LAN 免密时根路径直接进 dsh 工作台
            # （经 deepDDW 网关反代，零配置直达；dsh 保持 localhost 安全绑定）。
            # 外网/需 Token 才走启动页。
            from core.security.token_gate import client_ip, lan_bypass_enabled, is_lan_client

            if lan_bypass_enabled() and is_lan_client(client_ip(request)):
                return RedirectResponse(url="/dsh/")
            return RedirectResponse(url="/ui/deepddw-launcher.html")

        # ---- dsh 工作台反代（2026-08-16）：手机/浏览器只连 deepDDW 网关，
        #     网关把 /dsh/* 和 /api/*（dsh 的 RPC/API）代理到本机 dsh 引擎
        #     （127.0.0.1:3080，dsh 安全绑定 localhost）。避免直接暴露 dsh
        #     到局域网（dsh 拒绝 0.0.0.0：防远程代码执行）。
        #     可用 env DEEPDDW_DSH_URL 指向其他 dsh 地址。

        def _reject_cross_site_fetch(request: Request) -> None:
            """P0-7：拒绝跨站请求代理（sec-fetch-site 校验）。"""
            site = (request.headers.get("sec-fetch-site") or "").lower()
            if site in ("cross-site", "same-site"):
                raise HTTPException(
                    status_code=403, detail="cross-site proxy request rejected"
                )

        async def _proxy_client() -> httpx.AsyncClient:
            """P1-14：复用应用级 httpx client（lifespan 创建/关闭，避免每请求新建）。"""
            client = getattr(app.state, "ddw_proxy_client", None)
            if client is None:
                client = httpx.AsyncClient(timeout=120.0)
                app.state.ddw_proxy_client = client
            return client

        async def _proxy_to_dsh(path: str, request: Request, rewrite_html: bool, path_prefix: str = ""):
            """把请求转发到 dsh 引擎；rewrite_html 时重写 SPA 资源前缀 + 注入 polyfill。

            path_prefix：目标路径前缀。/dsh/{path} → 转发 {base}/{path}（页面在 dsh 根）；
            /api/{path} → 转发 {base}/api/{path}（dsh RPC 端点带 /api 前缀）。

            P0-7：``sec-fetch-site`` 校验——只允许 same-origin / none（顶层导航与
            网关同源页面），cross-site / same-site（外部站点经网关访问 dsh）一律
            403，防止任意站点借网关获得"dsh 同源"待遇绕过 browser-trust。
            """
            _reject_cross_site_fetch(request)

            dsh_base = os.environ.get("DEEPDDW_DSH_URL", "http://127.0.0.1:3080").rstrip("/")
            target = f"{dsh_base}{path_prefix}/{path}" if path else f"{dsh_base}{path_prefix}/"
            if request.url.query:
                target += f"?{request.url.query}"
            # 改写 Origin：dsh 的 browser-trust fence 只信任自身绑定地址的 Origin
            # （127.0.0.1:3080），手机经网关反代后 Origin 是网关地址 → 403。
            # 反代场景下把 Origin 改写为 dsh 自身地址，dsh 视为同源放行。
            headers = {k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length", "origin")}
            headers["Origin"] = dsh_base
            body = await request.body() if request.method in ("POST", "PUT", "DELETE") else None
            client = await _proxy_client()
            resp = await client.request(
                request.method, target, headers=headers, content=body,
                follow_redirects=False,
            )
            from fastapi.responses import Response

            content = resp.content
            ctype = resp.headers.get("content-type", "")
            if rewrite_html and "text/html" in ctype and content:
                text = content.decode("utf-8", errors="replace")
                text = (
                    text.replace('href="/', 'href="/dsh/')
                    .replace('src="/', 'src="/dsh/')
                    .replace('action="/', 'action="/dsh/')
                    .replace('fetch("/', 'fetch("/dsh/')
                    .replace('"url":"/', '"url":"/dsh/')
                    .replace("'url':'/", "'url':'/dsh/")
                )
                # 非安全上下文（HTTP 非 localhost，如手机经网关反代访问）没有
                # crypto.randomUUID → dsh 模型页"加载提供方目录失败"。注入 polyfill：
                # 用 crypto.getRandomValues 实现 UUID v4（getRandomValues 无需安全上下文）。
                polyfill = (
                    "<script>"
                    "if(window.crypto&&!window.crypto.randomUUID){(function(){"  # noqa: E501
                    "var c=new Uint8Array(16);"
                    "window.crypto.randomUUID=function(){"
                    "crypto.getRandomValues(c);c[6]=(c[6]&15)|64;c[8]=(c[8]&63)|128;"
                    "var h=function(b){return(b<16?'0':'')+b.toString(16)};"
                    "return h(c[0])+h(c[1])+h(c[2])+h(c[3])+'-'+h(c[4])+h(c[5])+'-'+"
                    "h(c[6])+h(c[7])+'-'+h(c[8])+h(c[9])+'-'+"
                    "h(c[10])+h(c[11])+h(c[12])+h(c[13])+h(c[14])+h(c[15])};})();}"
                    "</script>"
                )
                text = text.replace("</head>", polyfill + "</head>", 1)
                content = text.encode("utf-8")
            return Response(
                content=content,
                status_code=resp.status_code,
                headers={k: v for k, v in resp.headers.items() if k.lower() not in ("content-length", "transfer-encoding", "connection")},
                media_type=ctype,
            )

        @app.api_route("/dsh/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"], include_in_schema=False)
        async def dsh_proxy(path: str, request: Request):
            return await _proxy_to_dsh(path, request, rewrite_html=True, path_prefix="")

        # dsh 的 RPC/API 端点（/api/llm.providers 等）：浏览器经反代访问时请求发到
        # 网关根路径 /api/*（dsh 前端 API 基址 = location.origin）。
        # deepDDW 自己的 API 是 /api/v1/*，路径前缀不同不冲突；此处代理其余 /api/* 到 dsh。
        @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"], include_in_schema=False)
        async def dsh_api_proxy(path: str, request: Request):
            return await _proxy_to_dsh(path, request, rewrite_html=False, path_prefix="/api")

        # ---- dsh WebSocket 反代（2026-08-16）：dsh 对话/事件推送走 WebSocket
        #     （/api/events.mux 等）。普通 HTTP 反代不处理升级握手 → 403。
        #     用 websockets 库连接 dsh 并双向转发；Origin 改写为 dsh 自身地址过 fence。
        @app.websocket("/api/{path:path}")
        async def dsh_ws_proxy(websocket: WebSocket, path: str):
            import websockets

            # P0-7：跨站 WebSocket 升级请求拒绝（sec-fetch-site 校验）
            site = (websocket.headers.get("sec-fetch-site") or "").lower()
            if site in ("cross-site", "same-site"):
                await websocket.close(code=4403, reason="cross-site rejected")
                return
            await websocket.accept()
            # P0-3（multidevice）：设备在线跟踪——客户端 WS 带 ?device_id=xxx；
            # 连接期间心跳在线，关闭时离开（内存活跃表，60s 窗口）。
            device_id = (websocket.query_params.get("device_id") or "").strip()
            if device_id:
                from core.api import status as status_api

                status_api.touch_device(device_id)
                status_api.bump_ws_count(1)
            dsh_base = os.environ.get("DEEPDDW_DSH_URL", "http://127.0.0.1:3080").rstrip("/")
            ws_url = dsh_base.replace("http://", "ws://").replace("https://", "wss://")
            target = f"{ws_url}/api/{path}"
            if websocket.query_params:
                target += "?" + str(websocket.query_params)
            try:
                async with websockets.connect(
                    target,
                    additional_headers={"Origin": dsh_base},
                    open_timeout=10,
                ) as upstream:
                    async def pump_up():
                        try:
                            while True:
                                msg = await websocket.receive_text()
                                await upstream.send(msg)
                        except Exception:
                            pass

                    async def pump_down():
                        try:
                            async for msg in upstream:
                                if isinstance(msg, bytes):
                                    await websocket.send_bytes(msg)
                                else:
                                    await websocket.send_text(msg)
                        except Exception:
                            pass

                    import asyncio

                    await asyncio.gather(pump_up(), pump_down())
            except Exception as exc:  # noqa: BLE001
                logger.warning("dsh ws proxy failed: %s", exc)
            finally:
                try:
                    await websocket.close()
                except Exception:  # noqa: BLE001
                    pass
                if device_id:
                    from core.api import status as status_api

                    status_api.leave_device(device_id)
                    status_api.bump_ws_count(-1)
    else:
        logger.warning("frontend directory not found: %s", frontend)

    return app


app = create_app()


__all__ = ["app", "create_app", "load_plugins"]
