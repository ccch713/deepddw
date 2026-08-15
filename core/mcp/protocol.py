"""MCP 协议消息定义（DDW AI Hub v6.0 — 模块 D1，双协议）。

遵循 MCP 2024-11-05（经典）+ 2025-03-26（streamable-http）+ JSON-RPC 2.0。
版本协商：initialize 时返回客户端请求的协议版本（受支持时），
否则返回服务端最高版本（规范要求客户端必须支持服务端返回的版本）。

JSON-RPC 2.0 错误码：
- -32700 ParseError
- -32600 InvalidRequest
- -32601 MethodNotFound
- -32602 InvalidParams
- -32603 InternalError

MCP 特定错误码（server-defined）：
- -32001 ResourceNotFound
- -32002 ToolNotFound
- -32003 Unauthorized
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# 标准错误码
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# MCP 特定
RESOURCE_NOT_FOUND = -32001
TOOL_NOT_FOUND = -32002
UNAUTHORIZED = -32003

# 协议版本（双协议兼容，v6.0）
PROTOCOL_VERSION_2024_11_05 = "2024-11-05"
PROTOCOL_VERSION_2025_03_26 = "2025-03-26"
SUPPORTED_PROTOCOL_VERSIONS = [
    PROTOCOL_VERSION_2024_11_05,
    PROTOCOL_VERSION_2025_03_26,
]
# 服务端最高版本（未知版本时返回它）
HIGHEST_PROTOCOL_VERSION = PROTOCOL_VERSION_2025_03_26


def negotiate_protocol_version(requested: Optional[str]) -> str:
    """版本协商：请求版本受支持则返回之，否则返回服务端最高版本。"""
    if requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return HIGHEST_PROTOCOL_VERSION


@dataclass
class JsonRpcRequest:
    jsonrpc: str = "2.0"
    id: Any = None
    method: str = ""
    params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"jsonrpc": self.jsonrpc, "method": self.method}
        if self.id is not None:
            d["id"] = self.id
        if self.params:
            d["params"] = self.params
        return d


@dataclass
class JsonRpcResponse:
    jsonrpc: str = "2.0"
    id: Any = None
    result: Any = None
    error: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"jsonrpc": self.jsonrpc, "id": self.id}
        if self.error is not None:
            d["error"] = self.error
        else:
            d["result"] = self.result
        return d


def make_error(code: int, message: str, data: Any = None) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return err


def make_result(req_id: Any, result: Any) -> JsonRpcResponse:
    return JsonRpcResponse(id=req_id, result=result)


def make_error_resp(req_id: Any, code: int, message: str, data: Any = None) -> JsonRpcResponse:
    return JsonRpcResponse(id=req_id, error=make_error(code, message, data))


def new_request_id() -> str:
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# MCP 能力声明
# ---------------------------------------------------------------------------


SERVER_INFO = {
    "name": "deepddw",
    "version": "0.1.0",
    "vendor": "deepDDW community",
    "description": "deepDDW — 开源个人 AI 底座（DSH + 知识库 + 记忆 + 网关 + MCP）",
}


SERVER_CAPABILITIES = {
    "tools": {"listChanged": False},
    "resources": {"listChanged": False, "subscribe": False},
}


__all__ = [
    "HIGHEST_PROTOCOL_VERSION",
    "INTERNAL_ERROR",
    "PROTOCOL_VERSION_2024_11_05",
    "PROTOCOL_VERSION_2025_03_26",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "negotiate_protocol_version",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "PARSE_ERROR",
    "RESOURCE_NOT_FOUND",
    "SERVER_CAPABILITIES",
    "SERVER_INFO",
    "TOOL_NOT_FOUND",
    "UNAUTHORIZED",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "make_error",
    "make_error_resp",
    "make_result",
    "new_request_id",
]
