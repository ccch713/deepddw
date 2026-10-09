"""org_relay 路由（bindcode-v1 §3 端点 + 成员 LLM 端点 + 管理端）。

三层鉴权：
- 产品令牌（公网三件）：``Authorization: Bearer <产品令牌>``（兼容协议 §3
  ``X-Product-Key`` 头），每令牌限速 10 req/min（可配）；
- 成员令牌（chat/completions）：绑定流程下发的 access_token；
- 实例管理 Token（admin/*）：复用 core.security.token_gate 静态门禁，
  不暴露公网（部署边界由反代/防火墙承担，见插件 README）。

响应为协议原生形状（不走 core.api_response 信封）——App 按协议解析。
"""

from __future__ import annotations

import hmac
import json
import logging
import time
import uuid
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from core.llm_gateway import gateway as llm_gateway
from core.llm_gateway.base import ChatMessage as LLMChatMessage
from core.security.token_gate import require_access_token

from . import service
from .config import get_org_relay_config

logger = logging.getLogger(__name__)

PLUGIN_PREFIX = "/api/v1/plugins/ddw-org-relay"
PUB_PREFIX = "/api/v1/relay/org/pub"

VALID_ROLES = ("system", "user", "assistant")


# ------------------------------------------------------------------ #
# 产品令牌鉴权 + 限速（bindcode-v1 §6：绑定端点须有限速）
# ------------------------------------------------------------------ #

_rate_buckets: Dict[str, Deque[float]] = {}


def reset_rate_buckets() -> None:  # 测试钩子
    _rate_buckets.clear()


class _RateLimited(Exception):
    def __init__(self, retry_after: float):
        super().__init__("rate limited")
        self.retry_after = max(1, int(retry_after))


def _check_rate(token: str, limit: int, window: float) -> None:
    now = time.monotonic()
    hits = [ts for ts in _rate_buckets.get(token, ()) if now - ts < window]
    if len(hits) >= limit:
        raise _RateLimited(window)
    hits.append(now)
    _rate_buckets[token] = deque(hits, maxlen=max(limit * 10, 100))


def require_product_token(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_product_key: Optional[str] = Header(None),
) -> str:
    """产品令牌（可配多枚）+ 每令牌限速。"""
    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()
    token = bearer or (x_product_key or "").strip()
    cfg = get_org_relay_config()
    tokens = cfg["product_tokens"]
    if not tokens or not token or not any(hmac.compare_digest(token, t) for t in tokens):
        raise HTTPException(401, "bad product token")
    try:
        _check_rate(token, cfg["rate_limit_per_token"], cfg["rate_limit_window_seconds"])
    except _RateLimited as exc:
        raise HTTPException(
            429, "rate limited", headers={"Retry-After": str(exc.retry_after)}
        ) from None
    return token


def require_member_token(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """成员级 access_token → 绑定上下文（与实例管理 Token 权限完全隔离）。"""
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(401, "missing member access token")
    row = service.binding_for_token(token)
    if row is None:
        raise HTTPException(401, "invalid or revoked member access token")
    return {"binding": row, "user_id": row["user_id"], "org_id": row["org_id"]}


def resolve_server_base_url(request: Optional[Request] = None) -> str:
    """本实例 LLM 端点 base（OpenAI 兼容）：显式配置优先，否则按请求 Host 推导。

    不存在任何外部默认值——指向的始终是部署者自己的这个实例。
    公网（HTTPS 域名/反代后）部署务必显式配置 ``server_base_url``。
    """
    configured = get_org_relay_config()["server_base_url"]
    if configured:
        return configured.rstrip("/")
    if request is not None:
        return f"{request.url.scheme}://{request.url.netloc}{PLUGIN_PREFIX}"
    return PLUGIN_PREFIX


# ------------------------------------------------------------------ #
# 请求/响应模型
# ------------------------------------------------------------------ #

class BindReq(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=512)


class UserIdReq(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)


class ChatMessageIn(BaseModel):
    role: str
    content: str


class ChatCompletionsReq(BaseModel):
    model: Optional[str] = None  # 模型选择由部署者配置的路由规则决定，此处仅透传展示
    messages: List[ChatMessageIn] = Field(min_length=1)
    stream: bool = False
    temperature: Optional[float] = None


class OrgCreateReq(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    plan: str = "light"
    quota_requests: Optional[int] = None


class BindcodeReq(BaseModel):
    ttl_min: int = 15
    max_uses: int = 50
    count: int = 1
    note: Optional[str] = None


class RevokeCodesReq(BaseModel):
    code: Optional[str] = None  # 空=吊销该组织全部在册绑定码


class OrgStatusReq(BaseModel):
    status: str  # active | disabled


class OrgQuotaReq(BaseModel):
    quota_requests: Optional[int] = None  # null = 不限


class AdminUnbindReq(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)


# ------------------------------------------------------------------ #
# 协议三件（公网，产品令牌）
# ------------------------------------------------------------------ #

def build_router() -> APIRouter:
    router = APIRouter(tags=["org-relay"])

    @router.post(f"{PUB_PREFIX}/bind")
    async def pub_bind(
        req: BindReq, request: Request, _tok: str = Depends(require_product_token)
    ) -> Dict[str, Any]:
        try:
            result = service.do_bind(req.user_id, req.code)
        except service.ServiceError as exc:
            _log_meta("bind", user_id=req.user_id, ok=False, result=exc.message)
            raise HTTPException(exc.code, exc.message) from None
        _log_meta("bind", user_id=req.user_id, ok=True)
        org = result.get("org") or {}
        if not get_org_relay_config()["server_base_url"]:
            org["server_base_url"] = resolve_server_base_url(request)
        return result

    @router.post(f"{PUB_PREFIX}/unbind")
    async def pub_unbind(
        req: UserIdReq, _tok: str = Depends(require_product_token)
    ) -> Dict[str, Any]:
        result = service.do_unbind(req.user_id)
        _log_meta("unbind", user_id=req.user_id, ok=True)
        return result

    @router.get(f"{PUB_PREFIX}/me")
    async def pub_me(
        user_id: str, request: Request, _tok: str = Depends(require_product_token)
    ) -> Dict[str, Any]:
        result = service.org_state(user_id)
        if result["bound"] and not get_org_relay_config()["server_base_url"]:
            (result.get("org") or {})["server_base_url"] = resolve_server_base_url(request)
        _log_meta("me", user_id=user_id, ok=True, bound=result["bound"])
        return result

    # ---- 成员 LLM 端点（OpenAI 兼容；供给=部署者自配 llm_gateway 供应商） ----

    @router.post(f"{PLUGIN_PREFIX}/chat/completions")
    async def chat_completions(
        req: ChatCompletionsReq, ctx: Dict[str, Any] = Depends(require_member_token)
    ):
        org_id, user_id = ctx["org_id"], ctx["user_id"]
        if any(m.role not in VALID_ROLES for m in req.messages):
            raise HTTPException(400, "role must be one of system|user|assistant")
        try:
            service.check_and_count_quota(org_id, ctx["binding"]["org_quota"])
        except service.ServiceError as exc:
            raise HTTPException(exc.code, exc.message) from None

        messages = [LLMChatMessage(role=m.role, content=m.content) for m in req.messages]
        kwargs: Dict[str, Any] = {}
        if req.temperature is not None:
            kwargs["temperature"] = req.temperature

        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())

        if req.stream:
            return StreamingResponse(
                _stream_completion(completion_id, created, org_id, user_id, messages, kwargs),
                media_type="text/event-stream",
            )

        try:
            resp = await llm_gateway.chat(messages, **kwargs)
        except Exception as exc:  # noqa: BLE001 — 网关全链失败 → 502（OpenAI error 形状）
            logger.warning("org_relay chat gateway failed: %s", exc)
            service.record_chat_usage(org_id, user_id, model=None,
                                      tokens_in=0, tokens_out=0, ok=False)
            return _openai_error(502, "upstream_error", str(exc)[:200])
        ok = resp.finish_reason != "error"
        service.record_chat_usage(org_id, user_id, model=resp.model,
                                  tokens_in=resp.tokens_in, tokens_out=resp.tokens_out, ok=ok)
        if not ok:
            return _openai_error(502, "upstream_error", resp.content[:200])
        _log_meta("chat", user_id=user_id, org_id=org_id, ok=True, model=resp.model)
        return {
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": resp.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": resp.content},
                "finish_reason": resp.finish_reason or "stop",
            }],
            "usage": {
                "prompt_tokens": resp.tokens_in,
                "completion_tokens": resp.tokens_out,
                "total_tokens": resp.tokens_in + resp.tokens_out,
            },
        }

    # ---- 管理端（实例静态 Token 门禁；不暴露公网） ----

    @router.post(f"{PLUGIN_PREFIX}/admin/orgs")
    async def admin_create_org(
        req: OrgCreateReq, claims: Dict[str, Any] = Depends(require_access_token)
    ) -> Dict[str, Any]:
        result = service.create_org(req.name, req.plan, quota_requests=req.quota_requests)
        result["bindcode_endpoint"] = f"{PLUGIN_PREFIX}/admin/orgs/{result['org_id']}/bindcode"
        _log_meta("admin_create_org", org_id=result["org_id"])
        return result

    @router.get(f"{PLUGIN_PREFIX}/admin/orgs")
    async def admin_list_orgs(
        limit: int = 100, claims: Dict[str, Any] = Depends(require_access_token)
    ) -> Dict[str, Any]:
        items = service.list_orgs(limit)
        return {"items": items, "total": len(items)}

    @router.get(f"{PLUGIN_PREFIX}/admin/orgs/{{org_id}}")
    async def admin_org_detail(
        org_id: str, claims: Dict[str, Any] = Depends(require_access_token)
    ) -> Dict[str, Any]:
        return service.org_detail(org_id)

    @router.post(f"{PLUGIN_PREFIX}/admin/orgs/{{org_id}}/bindcode")
    async def admin_issue_bindcode(
        org_id: str, req: BindcodeReq, claims: Dict[str, Any] = Depends(require_access_token)
    ) -> Dict[str, Any]:
        cfg = get_org_relay_config()
        ttl = req.ttl_min if "ttl_min" in req.model_fields_set else cfg["bindcode_ttl_min"]
        uses = req.max_uses if "max_uses" in req.model_fields_set else cfg["bindcode_max_uses"]
        result = service.issue_bindcodes(org_id, ttl_min=ttl, max_uses=uses,
                                         count=req.count, note=req.note)
        _log_meta("admin_issue_bindcode", org_id=org_id, count=len(result["codes"]))
        return result

    @router.post(f"{PLUGIN_PREFIX}/admin/orgs/{{org_id}}/revoke-codes")
    async def admin_revoke_codes(
        org_id: str, req: RevokeCodesReq | None = None,
        claims: Dict[str, Any] = Depends(require_access_token)
    ) -> Dict[str, Any]:
        code = req.code if req is not None else None
        result = service.revoke_bindcodes(org_id, code=code)
        _log_meta("admin_revoke_codes", org_id=org_id, revoked=result["revoked"])
        return result

    @router.post(f"{PLUGIN_PREFIX}/admin/orgs/{{org_id}}/rotate-secret")
    async def admin_rotate_secret(
        org_id: str, claims: Dict[str, Any] = Depends(require_access_token)
    ) -> Dict[str, Any]:
        result = service.rotate_secret(org_id)
        _log_meta("admin_rotate_secret", org_id=org_id)
        return result

    @router.post(f"{PLUGIN_PREFIX}/admin/orgs/{{org_id}}/status")
    async def admin_set_status(
        org_id: str, req: OrgStatusReq, claims: Dict[str, Any] = Depends(require_access_token)
    ) -> Dict[str, Any]:
        return service.set_org_status(org_id, req.status)

    @router.post(f"{PLUGIN_PREFIX}/admin/orgs/{{org_id}}/quota")
    async def admin_set_quota(
        org_id: str, req: OrgQuotaReq, claims: Dict[str, Any] = Depends(require_access_token)
    ) -> Dict[str, Any]:
        return service.set_org_quota(org_id, req.quota_requests)

    @router.post(f"{PLUGIN_PREFIX}/admin/unbind")
    async def admin_unbind(
        req: AdminUnbindReq, claims: Dict[str, Any] = Depends(require_access_token)
    ) -> Dict[str, Any]:
        return service.admin_unbind(req.user_id)

    @router.post(f"{PLUGIN_PREFIX}/admin/revoke-member")
    async def admin_revoke_member(
        req: AdminUnbindReq, claims: Dict[str, Any] = Depends(require_access_token)
    ) -> Dict[str, Any]:
        return service.revoke_member(req.user_id)

    @router.get(f"{PLUGIN_PREFIX}/admin/usage")
    async def admin_usage(
        org_id: Optional[str] = None, limit: int = 50,
        claims: Dict[str, Any] = Depends(require_access_token)
    ) -> Dict[str, Any]:
        return service.usage_report(org_id, limit)

    # ---- 插件健康 + 协议版本声明（bindcode-v1 §7） ----

    @router.get(f"{PLUGIN_PREFIX}/health")
    async def plugin_health() -> Dict[str, Any]:
        from . import PLUGIN_NAME, VERSION

        return {
            "status": "ok",
            "plugin": PLUGIN_NAME,
            "version": VERSION,
            "protocol": "bindcode",
            "protocol_version": "1",
        }

    return router


# ------------------------------------------------------------------ #
# 流式与辅助
# ------------------------------------------------------------------ #

async def _stream_completion(
    completion_id: str, created: int, org_id: str, user_id: str,
    messages: List[LLMChatMessage], kwargs: Dict[str, Any],
):
    """OpenAI SSE 形状流式输出；token 数按产出块数记入元数据流水。"""
    chunks = 0
    try:
        async for token in llm_gateway.stream_chat(messages, **kwargs):
            chunks += 1
            yield _sse_chunk(completion_id, created, token)
        yield _sse_chunk(completion_id, created, "")
        yield "data: [DONE]\n\n"
        service.record_chat_usage(org_id, user_id, model=None,
                                  tokens_in=0, tokens_out=chunks, ok=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("org_relay stream failed: %s", exc)
        service.record_chat_usage(org_id, user_id, model=None,
                                  tokens_in=0, tokens_out=chunks, ok=False)
        yield _sse_error(502, "upstream_error", str(exc)[:200])


def _sse_chunk(completion_id: str, created: int, content: str) -> str:
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "choices": [{"index": 0, "delta": {"content": content} if content else {},
                     "finish_reason": None}],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sse_error(status: int, err_type: str, message: str) -> str:
    return f"data: {json.dumps({'error': {'type': err_type, 'message': message}})}\n\n"


def _openai_error(status: int, err_type: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"type": err_type, "message": message}})


def _log_meta(action: str, **fields: Any) -> None:
    """仅元数据日志（§6）：org_id/user_id/动作/结果，不落正文。"""
    parts = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    logger.info("org_relay %s %s", action, parts)
