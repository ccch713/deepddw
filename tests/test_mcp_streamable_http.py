"""MCP 双协议兼容（v6.0）测试：streamable-http 握手/会话/工具 + 经典回归 + 版本协商。

验收对齐规格书 §4：
- streamable-http 单端点 POST /api/v1/mcp（Mcp-Session-Id / Accept 协商 /
  无 session 非 initialize → 400）
- 版本协商（2025-03-26 / 2024-11-05 / 未知 → 最高版）
- tools/list 返回 DDW 工具；tools/call 真实返回 handler 结果
- 经典端点（/jsonrpc /info）行为不变
"""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi import FastAPI, Response

from core.mcp.protocol import (
    HIGHEST_PROTOCOL_VERSION,
    PROTOCOL_VERSION_2024_11_05,
    PROTOCOL_VERSION_2025_03_26,
)

MCP_BASE = "/api/v1/mcp"


@pytest.fixture(scope="module")
def mcp_app() -> FastAPI:
    """mini app：经典三端点 + streamable-http 单端点（与 main.py 挂载一致）。

    session manager 生命周期由 _RootPathNormalizer 惰性初始化（首次请求进入
    run() 上下文，pytest.ini 配置 session 级 loop 保证常驻）；不在 fixture 中
    手动 async with run()，避免 pytest-asyncio teardown 跨 task 退出 cancel scope。
    """
    from core.mcp.server import get_mcp_server
    from core.mcp.streamable_http import register_streamable_http

    app = FastAPI()

    # 经典端点（与 core/main.py 相同逻辑，向后兼容）
    from core.mcp.protocol import SERVER_CAPABILITIES, SERVER_INFO

    @app.get(f"{MCP_BASE}/info")
    async def mcp_info():
        return {"serverInfo": SERVER_INFO, "capabilities": SERVER_CAPABILITIES}

    @app.post(f"{MCP_BASE}/jsonrpc")
    async def mcp_jsonrpc(payload: dict):
        mcp = get_mcp_server()
        result = await mcp.handle_request(payload, context={"request": "http"})
        if result is None:
            return Response(status_code=204)
        return result

    # streamable-http 单端点（官方 SDK，Route 精确匹配，无 307）
    register_streamable_http(app)
    return app


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
) -> httpx.Response:
    """streamable-http 端点请求（带规范要求的 Content-Type / Accept / 会话头）。"""
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    return await client.post(MCP_BASE, headers=headers, content=payload)


def _sse_json(resp: httpx.Response) -> dict:
    """SDK streamable-http 以 text/event-stream 返回：解析 event: message 的 data。"""
    assert "text/event-stream" in resp.headers.get("content-type", ""), resp.headers
    data_lines = [ln for ln in resp.text.splitlines() if ln.startswith("data: ")]
    assert data_lines, resp.text
    return json.loads(data_lines[-1].removeprefix("data: "))


# ---------------------------------------------------------------------------
# 1. streamable-http 握手与版本协商
# ---------------------------------------------------------------------------


async def test_handshake_negotiates_2025(client):
    """声明 2025-03-26 → 协商返回 2025-03-26 + 首响应携带 Mcp-Session-Id。"""
    resp = await _stream_post(client, _initialize_payload(PROTOCOL_VERSION_2025_03_26))
    assert resp.status_code == 200
    assert "mcp-session-id" in resp.headers, resp.headers
    data = _sse_json(resp)
    assert data["result"]["protocolVersion"] == PROTOCOL_VERSION_2025_03_26
    assert data["result"]["serverInfo"]["version"] == "6.0.0"


async def test_handshake_negotiates_classic(client):
    """声明 2024-11-05 → 协商返回 2024-11-05。"""
    resp = await _stream_post(client, _initialize_payload(PROTOCOL_VERSION_2024_11_05))
    assert resp.status_code == 200
    data = _sse_json(resp)
    assert data["result"]["protocolVersion"] == PROTOCOL_VERSION_2024_11_05


async def test_session_required_for_non_initialize(client):
    """无 Mcp-Session-Id 且非 initialize → 400（规范要求）。"""
    resp = await _stream_post(client, _rpc("tools/list", {}))
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 2. tools/list 与 tools/call（会话内）
# ---------------------------------------------------------------------------


async def test_tools_list_with_session(client):
    """initialize 建立会话 → 带 session 调 tools/list → 返回 DDW 工具。"""
    init = await _stream_post(client, _initialize_payload(PROTOCOL_VERSION_2025_03_26))
    session_id = init.headers["mcp-session-id"]
    resp = await _stream_post(client, _rpc("tools/list", {}), session_id=session_id)
    assert resp.status_code == 200
    names = [t["name"] for t in _sse_json(resp)["result"]["tools"]]
    assert "ddw.llm.chat" in names
    assert "ddw.kb.search" in names


async def test_tools_call_kb_search_returns_real_result(client):
    """带 session 调 tools/call ddw.kb.search → 真实返回 handler 结果。"""
    init = await _stream_post(client, _initialize_payload(PROTOCOL_VERSION_2025_03_26))
    session_id = init.headers["mcp-session-id"]
    resp = await _stream_post(
        client,
        _rpc("tools/call", {"name": "ddw.kb.search", "arguments": {"query": "SPC"}}),
        session_id=session_id,
    )
    assert resp.status_code == 200
    result = _sse_json(resp)["result"]
    # SDK 将 handler 的 dict 返回序列化为 content 文本
    text = json.dumps(result, ensure_ascii=False)
    assert "SPC" in text


# ---------------------------------------------------------------------------
# 3. 经典端点回归 + 版本协商（手写路径）
# ---------------------------------------------------------------------------


async def test_classic_endpoints_regression(client):
    """经典 /info 与 /jsonrpc tools/list 行为不变。"""
    info = await client.get(f"{MCP_BASE}/info")
    assert info.status_code == 200
    assert info.json()["serverInfo"]["version"] == "6.0.0"

    jsonrpc = await client.post(
        f"{MCP_BASE}/jsonrpc",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert jsonrpc.status_code == 200
    tools = jsonrpc.json()["result"]["tools"]
    assert any(t["name"] == "ddw.kb.search" for t in tools)


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


async def test_classic_negotiation_explicit_classic():
    """经典路径：声明 2024-11-05 → 返回 2024-11-05。"""
    from core.mcp.server import get_mcp_server

    mcp = get_mcp_server()
    resp = await mcp.handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION_2024_11_05},
        },
        context={},
    )
    assert resp["result"]["protocolVersion"] == PROTOCOL_VERSION_2024_11_05
