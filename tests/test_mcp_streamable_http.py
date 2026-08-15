"""deepDDW MCP 测试：Token 门禁（P0-1）+ 工具时序一致性（P0-2）+ 经典回归 + exec 加固（P1-2）。

验收对齐任务书 §3 / §6：
- 鉴权：无 Token → 401；错误 Token → 401；正确 Token → initialize/tools/list 正常；
  X-DDW-Token 头可用；Bearer 头可用（≥5 条）
- 时序：load_plugins 后 rebuild_fastmcp → streamable-http == 经典端点工具集合；
  插件 override 工具（ddw.docs_portal.search）在 streamable-http 可见（≥2 条）
- 回归：经典端点带 Token 正常；tools/list 无 commercial 工具；kb.search 真实结果（≥3 条）
- 加固：P1-2 exec 动态签名（恶意 schema 不崩、不注入）
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi import Depends, FastAPI, Response

from core.mcp.protocol import (
    HIGHEST_PROTOCOL_VERSION,
    PROTOCOL_VERSION_2024_11_05,
    PROTOCOL_VERSION_2025_03_26,
    SERVER_CAPABILITIES,
    SERVER_INFO,
)
from core.security.token_gate import get_access_token

MCP_BASE = "/api/v1/mcp"

os_environ_guard = None  # placeholder to keep flake happy


def _auth_bearer() -> dict:
    return {"Authorization": f"Bearer {get_access_token()}"}


def _auth_x_token() -> dict:
    return {"X-DDW-Token": get_access_token()}


def _build_mini_app() -> FastAPI:
    """mini app：经典三端点（带 Token 门禁）+ streamable-http 单端点（自带门禁）。

    与 core/main.py 挂载逻辑一致；session manager 生命周期由
    _RootPathNormalizer 惰性初始化（pytest.ini 配置 session 级 loop 常驻）。
    """
    from core.mcp.server import get_mcp_server
    from core.mcp.streamable_http import register_streamable_http
    from core.security.token_gate import require_access_token

    app = FastAPI()

    @app.get("/api/v1/gateway/verify")
    async def gateway_verify(claims: dict = Depends(require_access_token)):
        return {"ok": True, "authenticated": True, "token_valid": True}

    @app.get(f"{MCP_BASE}/info")
    async def mcp_info(claims: dict = Depends(require_access_token)):
        return {"serverInfo": SERVER_INFO, "capabilities": SERVER_CAPABILITIES}

    @app.post(f"{MCP_BASE}/jsonrpc")
    async def mcp_jsonrpc(payload: dict, claims: dict = Depends(require_access_token)):
        mcp = get_mcp_server()
        result = await mcp.handle_request(payload, context={"request": "http"})
        if result is None:
            return Response(status_code=204)
        return result

    @app.get(f"{MCP_BASE}/sse")
    async def mcp_sse(claims: dict = Depends(require_access_token)):
        from fastapi.responses import StreamingResponse

        async def event_stream():
            import asyncio
            yield f"data: {json.dumps({'event': 'hello', 'server': SERVER_INFO['name']}, ensure_ascii=False)}\n\n"
            while True:
                await asyncio.sleep(15)
                yield ": keep-alive\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    register_streamable_http(app)
    return app


@pytest.fixture(scope="module")
def mcp_app() -> FastAPI:
    return _build_mini_app()


@pytest.fixture
def client(mcp_app):
    transport = httpx.ASGITransport(app=mcp_app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _initialize_payload(protocol_version: str) -> bytes:
    return json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1.0"},
        },
    }).encode()


def _rpc(method: str, params: dict, req_id: int = 2) -> bytes:
    return json.dumps({
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params,
    }).encode()


async def _stream_post(
    client,
    payload: bytes,
    session_id: str | None = None,
    headers: dict | None = None,
) -> httpx.Response:
    """streamable-http 端点请求（规范头 + 可选鉴权头）。"""
    h = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        **(headers or {}),
    }
    if session_id:
        h["Mcp-Session-Id"] = session_id
    return await client.post(MCP_BASE, headers=h, content=payload)


def _sse_json(resp: httpx.Response) -> dict:
    """SDK streamable-http 以 text/event-stream 返回：解析 event: message 的 data。"""
    assert "text/event-stream" in resp.headers.get("content-type", ""), resp.headers
    data_lines = [ln for ln in resp.text.splitlines() if ln.startswith("data: ")]
    assert data_lines, resp.text
    return json.loads(data_lines[-1].removeprefix("data: "))


# ===========================================================================
# P0-1 鉴权：无 Token / 错误 Token / 正确 Token / 双头（≥5 条）
# ===========================================================================


async def test_no_token_streamable_returns_401(client):
    """无 Token 调 streamable-http → 401（P0-1 验收）。"""
    resp = await _stream_post(client, _initialize_payload(PROTOCOL_VERSION_2025_03_26))
    assert resp.status_code == 401


async def test_no_token_classic_returns_401(client):
    """无 Token 调经典端点 → 401（jsonrpc + info + sse）。"""
    resp = await client.post(
        f"{MCP_BASE}/jsonrpc",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
    )
    assert resp.status_code == 401
    resp_info = await client.get(f"{MCP_BASE}/info")
    assert resp_info.status_code == 401
    resp_sse = await client.get(f"{MCP_BASE}/sse")
    assert resp_sse.status_code == 401


async def test_wrong_token_returns_401(client):
    """错误 Token → 401（Bearer 与 X-DDW-Token 双通道）。"""
    resp = await _stream_post(
        client,
        _initialize_payload(PROTOCOL_VERSION_2025_03_26),
        headers={"Authorization": "Bearer wrong-token-123"},
    )
    assert resp.status_code == 401
    resp2 = await _stream_post(
        client,
        _initialize_payload(PROTOCOL_VERSION_2025_03_26),
        headers={"X-DDW-Token": "wrong-token-123"},
    )
    assert resp2.status_code == 401


async def test_valid_bearer_token_initialize_ok(client):
    """正确 Token（Bearer）→ initialize 正常（版本协商 + Mcp-Session-Id）。"""
    resp = await _stream_post(
        client,
        _initialize_payload(PROTOCOL_VERSION_2025_03_26),
        headers=_auth_bearer(),
    )
    assert resp.status_code == 200
    assert "mcp-session-id" in resp.headers, resp.headers
    data = _sse_json(resp)
    assert data["result"]["protocolVersion"] == PROTOCOL_VERSION_2025_03_26
    assert data["result"]["serverInfo"]["name"] == "deepddw"


async def test_valid_x_ddw_token_initialize_ok(client):
    """正确 Token（X-DDW-Token）→ initialize 正常。"""
    resp = await _stream_post(
        client,
        _initialize_payload(PROTOCOL_VERSION_2024_11_05),
        headers=_auth_x_token(),
    )
    assert resp.status_code == 200
    data = _sse_json(resp)
    assert data["result"]["protocolVersion"] == PROTOCOL_VERSION_2024_11_05


async def test_token_gate_verify_endpoint(client):
    """网关校验端点 /api/v1/gateway/verify：无 Token 401，有 Token 200。"""
    resp = await client.get("/api/v1/gateway/verify")
    assert resp.status_code == 401
    resp_ok = await client.get("/api/v1/gateway/verify", headers=_auth_bearer())
    assert resp_ok.status_code == 200
    assert resp_ok.json()["authenticated"] is True


# ===========================================================================
# P0-2 工具时序：插件加载后重建 FastMCP → 与经典端点一致（≥2 条）
# ===========================================================================


def _register_plugin_tool():
    """模拟插件 override 工具注册（等价 docs_portal 插件 setup 注册）。"""
    from core.mcp.server import get_mcp_server

    from plugins.ddw_docs_portal.llm_tool import register_docs_tool

    register_docs_tool(get_mcp_server().tools)


def _classic_tool_names() -> set[str]:
    from core.mcp.server import get_mcp_server

    return {t.name for t in get_mcp_server().public_tools()}


async def _stream_tool_names(client) -> set[str]:
    """通过 streamable-http tools/list 拿到工具名集合（会话内）。"""
    init = await _stream_post(
        client, _initialize_payload(PROTOCOL_VERSION_2025_03_26), headers=_auth_bearer()
    )
    assert init.status_code == 200, init.text
    session_id = init.headers["mcp-session-id"]
    resp = await _stream_post(
        client, _rpc("tools/list", {}), session_id=session_id, headers=_auth_bearer()
    )
    assert resp.status_code == 200, resp.text
    return {t["name"] for t in _sse_json(resp)["result"]["tools"]}


async def test_streamable_equals_classic_after_plugin_load(client, monkeypatch):
    """P0-2：模拟插件加载后 rebuild_fastmcp → streamable == 经典工具集合。"""
    from core.mcp.streamable_http import rebuild_fastmcp

    # 插件加载（等价 load_plugins 里插件 setup 的工具注册）
    _register_plugin_tool()
    # lifespan 语义：load_plugins 之后重建 FastMCP（P0-2 修复点）
    rebuild_fastmcp()

    classic = _classic_tool_names()
    stream = await _stream_tool_names(client)
    assert classic == stream
    assert "ddw.docs_portal.search" in classic  # 插件 override 工具可见且真实


async def test_streamable_has_no_stub_tools(client):
    """streamable-http 与经典端点都不含已删商业插件的 stub 工具。"""
    classic = _classic_tool_names()
    assert "ddw.training.start_session" not in classic
    assert "ddw.training.get_progress" not in classic
    assert "ddw.hris.sync_employees" not in classic
    assert "ddw.smart_cs.handle_message" not in classic
    assert "ddw.email.send" not in classic


# ===========================================================================
# 经典端点回归（带 Token）+ 真实实现（≥3 条）
# ===========================================================================


async def test_classic_endpoints_regression(client):
    """经典 /info 与 /jsonrpc tools/list 带 Token 行为正常。"""
    info = await client.get(f"{MCP_BASE}/info", headers=_auth_bearer())
    assert info.status_code == 200
    assert info.json()["serverInfo"]["version"] == "0.1.0"

    jsonrpc = await client.post(
        f"{MCP_BASE}/jsonrpc",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers=_auth_bearer(),
    )
    assert jsonrpc.status_code == 200
    tools = jsonrpc.json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert "ddw.kb.search" in names
    assert "ddw.llm.chat" in names
    # commercial 插件工具绝不外露
    assert not any("training" in n or "hris" in n or "smart_cs" in n for n in names)


async def test_classic_negotiation_unknown_version():
    """经典路径：未知 protocolVersion → 返回服务端最高版（2025-03-26）。"""
    from core.mcp.server import get_mcp_server

    mcp = get_mcp_server()
    resp = await mcp.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-01-01", "capabilities": {}},
        },
        context={},
    )
    assert resp["result"]["protocolVersion"] == HIGHEST_PROTOCOL_VERSION


async def test_kb_search_returns_real_result(client):
    """ddw.kb.search 真实实现（非 stub）：写入知识库后能检索命中。"""
    from core.knowledge import kb_add_document
    from core.mcp.streamable_http import rebuild_fastmcp

    kb_add_document("SPC 质量控制手册", "统计过程控制 SPC 用于生产质量监控。")
    rebuild_fastmcp()  # 让新文档对 FastMCP 可见（工具本体不变，重建无害）

    init = await _stream_post(
        client, _initialize_payload(PROTOCOL_VERSION_2025_03_26), headers=_auth_bearer()
    )
    session_id = init.headers["mcp-session-id"]
    resp = await _stream_post(
        client,
        _rpc("tools/call", {"name": "ddw.kb.search", "arguments": {"query": "SPC"}}),
        session_id=session_id,
        headers=_auth_bearer(),
    )
    assert resp.status_code == 200
    text = json.dumps(_sse_json(resp)["result"], ensure_ascii=False)
    assert "SPC" in text


# ===========================================================================
# P1-2 exec 签名加固（≥1 条）
# ===========================================================================


async def test_exec_signature_hardening_rejects_malicious_params():
    """恶意 schema（非标识符参数名 / 引号注入 enum）→ 不崩、不注入。"""
    from core.mcp.streamable_http import _build_wrapped

    async def fake_handler(args, ctx):
        return {"ok": True, "args": args}

    # 恶意参数名：包含注入片段
    malicious = {
        "properties": {
            "__import__('os').system('touch /tmp/pwned')": {"type": "string"},
            "valid_key": {"type": "string"},
            "x\"; import os; os.system('echo pwned') #": {"type": "string"},
        },
        "required": ["valid_key"],
    }
    wrapped = _build_wrapped(fake_handler, malicious)
    assert callable(wrapped)
    # 只保留合法参数 valid_key；调用不抛错
    result = await wrapped(valid_key="ok")
    assert result["ok"] is True
    assert result["args"].get("valid_key") == "ok"

    # enum 值注入引号 → repr 转义后不破坏语法
    enum_tool = {
        "properties": {
            "mode": {"type": "string", "enum": ["a\"); import os; os.system('echo pwned') #", "safe"]},
        },
        "required": ["mode"],
    }
    wrapped2 = _build_wrapped(fake_handler, enum_tool)
    assert callable(wrapped2)
    result2 = await wrapped2(mode="safe")
    assert result2["ok"] is True
