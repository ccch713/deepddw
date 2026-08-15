"""
FastAPI 路由 — LLM Gateway API 端点

映射源: One API router/relay.go + controller/channel.go + controller/channel-test.go

端点列表:
- POST /v1/chat/completions      — Chat Completion 转发（OpenAI 兼容）
- POST /v1/completions           — Text Completion 转发
- POST /v1/embeddings            — Embedding 转发
- POST /v1/images/generations    — 图像生成转发
- GET  /v1/models                — 可用模型列表
- GET  /api/gateway/channels     — 渠道列表（管理）
- POST /api/gateway/channels     — 创建渠道
- PUT  /api/gateway/channels/{id} — 更新渠道
- DELETE /api/gateway/channels/{id} — 删除渠道
- POST /api/gateway/channels/{id}/test — 手动测试渠道
- POST /api/gateway/channels/test-all  — 批量测试所有渠道
- GET  /api/gateway/dashboard    — 网关 Dashboard
- GET  /health                   — 健康检查
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["llm-gateway"])


# ── API Key 鉴权 ──

class APIKeyAuth:
    """
    API Key 鉴权管理器

    支持多 key 轮换，从请求头 X-API-Key 读取。
    若未配置任何 key，则跳过鉴权（向后兼容）。
    """

    def __init__(self, keys: list[str] | None = None) -> None:
        self._keys: set[str] = set(keys or [])

    @classmethod
    def from_env(cls, env_var: str = "DDW_GATEWAY_API_KEYS") -> "APIKeyAuth":
        """从环境变量加载，逗号分隔"""
        raw = os.environ.get(env_var, "")
        keys = [k.strip() for k in raw.split(",") if k.strip()]
        return cls(keys)

    def is_configured(self) -> bool:
        return len(self._keys) > 0

    def validate(self, key: str | None) -> bool:
        """校验 key，未配置时始终放行"""
        if not self._keys:
            return True
        return key in self._keys

    def add_key(self, key: str) -> None:
        self._keys.add(key)

    def remove_key(self, key: str) -> None:
        self._keys.discard(key)

    def list_keys(self) -> list[str]:
        """返回脱敏 key 列表（仅前 4 位 + ***）"""
        return [f"{k[:4]}***" for k in self._keys]


# 全局鉴权实例（延迟初始化）
_api_key_auth: APIKeyAuth | None = None


def get_api_key_auth() -> APIKeyAuth:
    """获取全局 API Key 鉴权实例"""
    global _api_key_auth
    if _api_key_auth is None:
        _api_key_auth = APIKeyAuth.from_env()
    return _api_key_auth


def set_api_key_auth(auth: APIKeyAuth) -> None:
    """设置全局 API Key 鉴权实例（用于测试或运行时配置）"""
    global _api_key_auth
    _api_key_auth = auth


async def _verify_api_key(request: Request) -> None:
    """FastAPI 依赖：校验 X-API-Key 请求头"""
    auth = get_api_key_auth()
    if not auth.is_configured():
        return
    api_key = request.headers.get("X-API-Key")
    if not auth.validate(api_key):
        raise HTTPException(
            status_code=401,
            detail={"error": {"message": "无效或缺失的 API Key"}},
        )


# 鉴权依赖（可被测试替换）
_require_api_key = Depends(_verify_api_key)


# ── Pydantic 请求/响应模型 ──

class ChatCompletionRequest(BaseModel):
    """Chat Completion 请求 — OpenAI 兼容格式"""
    model: str = Field(..., description="模型名称")
    messages: list[dict[str, Any]] = Field(default_factory=list, description="消息列表")
    max_tokens: Optional[int] = Field(None, description="最大 token 数")
    temperature: Optional[float] = Field(None, description="温度")
    top_p: Optional[float] = Field(None, description="Top P")
    stream: bool = Field(False, description="是否流式输出")
    user: Optional[str] = Field(None, description="用户标识")


class CompletionRequest(BaseModel):
    """Text Completion 请求"""
    model: str = Field(..., description="模型名称")
    prompt: str = Field("", description="提示词")
    max_tokens: Optional[int] = Field(None, description="最大 token 数")
    temperature: Optional[float] = Field(None, description="温度")
    stream: bool = Field(False, description="是否流式输出")


class EmbeddingRequest(BaseModel):
    """Embedding 请求"""
    model: str = Field(..., description="模型名称")
    input: str | list[str] = Field(..., description="输入文本")


class ImageGenerationRequest(BaseModel):
    """图像生成请求"""
    model: str = Field("", description="模型名称")
    prompt: str = Field(..., description="提示词")
    n: int = Field(1, description="生成数量")
    size: str = Field("1024x1024", description="图像尺寸")


class ChannelCreateRequest(BaseModel):
    """创建渠道请求"""
    name: str = Field(..., description="渠道名称")
    type: int = Field(..., description="渠道类型（ChannelType 枚举值）")
    key: str = Field("", description="API 密钥")
    base_url: str = Field("", description="基础 URL")
    models: list[str] = Field(default_factory=list, description="支持的模型列表")
    priority: int = Field(0, description="优先级")
    weight: int = Field(0, description="权重")
    group: str = Field("default", description="分组")
    config: dict[str, Any] = Field(default_factory=dict, description="渠道特定配置")


class ChannelUpdateRequest(BaseModel):
    """更新渠道请求"""
    name: Optional[str] = Field(None, description="渠道名称")
    key: Optional[str] = Field(None, description="API 密钥")
    base_url: Optional[str] = Field(None, description="基础 URL")
    models: Optional[list[str]] = Field(None, description="支持的模型列表")
    priority: Optional[int] = Field(None, description="优先级")
    weight: Optional[int] = Field(None, description="权重")
    group: Optional[str] = Field(None, description="分组")
    status: Optional[int] = Field(None, description="状态")
    config: Optional[dict[str, Any]] = Field(None, description="渠道特定配置")


# ── 状态存储（内存，实际应使用数据库）──

_channel_manager = None
_circuit_breaker = None
_health_monitor = None
_load_balancer = None


def _get_channel_manager():
    """获取渠道管理器（延迟初始化）"""
    global _channel_manager
    if _channel_manager is None:
        from .channel_manager import ChannelManager
        _channel_manager = ChannelManager()
    return _channel_manager


def _get_circuit_breaker():
    """获取断路器"""
    global _circuit_breaker
    if _circuit_breaker is None:
        from .circuit_breaker import CircuitBreaker
        _circuit_breaker = CircuitBreaker()
    return _circuit_breaker


def _get_health_monitor():
    """获取健康监控"""
    global _health_monitor
    if _health_monitor is None:
        from .health_monitor import ChannelHealthMonitor
        _health_monitor = ChannelHealthMonitor(
            channel_manager=_get_channel_manager(),
            circuit_breaker=_get_circuit_breaker(),
        )
    return _health_monitor


def _get_load_balancer():
    """获取负载均衡器"""
    global _load_balancer
    if _load_balancer is None:
        from .load_balancer import LoadBalancer
        _load_balancer = LoadBalancer()
    return _load_balancer


# ── OpenAI 兼容端点 ──

@router.post("/v1/chat/completions", dependencies=[_require_api_key])
async def chat_completions(request: Request) -> Any:
    """
    Chat Completion 转发（OpenAI 兼容）

    对应 One API: router/relay.go → controller/text.go:TextHelper()
    """
    try:
        body = await request.json()
        model = body.get("model", "")

        # 获取渠道管理器和负载均衡器
        cm = _get_channel_manager()
        lb = _get_load_balancer()

        # 获取支持该模型的启用渠道
        channels = cm.list_by_model(model)

        if not channels:
            return JSONResponse(
                status_code=404,
                content={"error": {"message": f"无可用渠道支持模型: {model}"}},
            )

        # 转换为 ChannelCandidate
        from .load_balancer import ChannelCandidate
        candidates = [
            ChannelCandidate(
                id=ch.id,
                name=ch.name,
                priority=ch.priority,
                weight=ch.weight,
                response_time=ch.response_time,
                balance=ch.balance,
                success_rate=1.0,  # 默认成功率
                models=ch.get_model_list(),
            )
            for ch in channels
        ]

        # 选择渠道
        selected = lb.select(candidates, model=model)

        if not selected:
            return JSONResponse(
                status_code=503,
                content={"error": {"message": "负载均衡器无法选择渠道"}},
            )

        # 返回响应（占位，实际应转发到上游）
        return {
            "id": f"chatcmpl-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"[LLM Gateway] 转发到渠道 {selected.name}",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }

    except Exception as e:
        logger.error("Chat Completion 转发失败: %s", e)
        return JSONResponse(
            status_code=500,
            content={"error": {"message": str(e)}},
        )


@router.post("/v1/completions", dependencies=[_require_api_key])
async def completions(request: Request) -> Any:
    """Text Completion 转发"""
    try:
        body = await request.json()
        return {
            "id": f"cmpl-{int(time.time())}",
            "object": "text_completion",
            "created": int(time.time()),
            "model": body.get("model", ""),
            "choices": [
                {
                    "index": 0,
                    "text": "[LLM Gateway] Text Completion 占位",
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": {"message": str(e)}})


@router.post("/v1/embeddings", dependencies=[_require_api_key])
async def embeddings(request: Request) -> Any:
    """Embedding 转发"""
    try:
        body = await request.json()
        return {
            "object": "list",
            "data": [
                {
                    "object": "embedding",
                    "index": 0,
                    "embedding": [0.0] * 1536,  # 占位
                }
            ],
            "model": body.get("model", ""),
            "usage": {
                "prompt_tokens": 0,
                "total_tokens": 0,
            },
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": {"message": str(e)}})


@router.post("/v1/images/generations", dependencies=[_require_api_key])
async def image_generations(request: Request) -> Any:
    """图像生成转发"""
    try:
        return {
            "created": int(time.time()),
            "data": [],
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": {"message": str(e)}})


@router.get("/v1/models", dependencies=[_require_api_key])
async def list_models() -> Any:
    """
    可用模型列表

    对应 One API: controller/model.go
    """
    cm = _get_channel_manager()
    all_models: set[str] = set()

    for channel in cm.list_enabled():
        all_models.update(channel.get_model_list())

    return {
        "object": "list",
        "data": [
            {
                "id": model,
                "object": "model",
                "created": 0,
                "owned_by": "llm-gateway",
            }
            for model in sorted(all_models)
        ],
    }


# ── 管理端点 ──

@router.get("/api/gateway/channels", dependencies=[_require_api_key])
async def list_channels() -> Any:
    """渠道列表（管理）"""
    cm = _get_channel_manager()
    channels = cm.list_all()
    return {
        "channels": [ch.to_dict() for ch in channels],
        "total": len(channels),
    }


@router.post("/api/gateway/channels", dependencies=[_require_api_key])
async def create_channel(request: Request) -> Any:
    """创建渠道"""
    try:
        body = await request.json()
        cm = _get_channel_manager()

        channel = cm.create(
            name=body["name"],
            channel_type=body["type"],
            key=body.get("key", ""),
            base_url=body.get("base_url", ""),
            models=body.get("models", []),
            priority=body.get("priority", 0),
            weight=body.get("weight", 0),
            group=body.get("group", "default"),
            config=body.get("config", {}),
        )

        return {"channel": channel.to_dict()}

    except KeyError as e:
        return JSONResponse(
            status_code=400,
            content={"error": {"message": f"缺少必填字段: {e}"}},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": {"message": str(e)}},
        )


@router.put("/api/gateway/channels/{channel_id}", dependencies=[_require_api_key])
async def update_channel(channel_id: int, request: Request) -> Any:
    """更新渠道"""
    try:
        body = await request.json()
        cm = _get_channel_manager()

        # 过滤 None 值
        update_data = {k: v for k, v in body.items() if v is not None}

        channel = cm.update(channel_id, **update_data)
        if not channel:
            return JSONResponse(
                status_code=404,
                content={"error": {"message": f"渠道 {channel_id} 不存在"}},
            )

        return {"channel": channel.to_dict()}

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": {"message": str(e)}},
        )


@router.delete("/api/gateway/channels/{channel_id}", dependencies=[_require_api_key])
async def delete_channel(channel_id: int) -> Any:
    """删除渠道"""
    cm = _get_channel_manager()
    success = cm.delete(channel_id)
    if not success:
        return JSONResponse(
            status_code=404,
            content={"error": {"message": f"渠道 {channel_id} 不存在"}},
        )
    return {"message": f"渠道 {channel_id} 已删除"}


@router.post("/api/gateway/channels/{channel_id}/test", dependencies=[_require_api_key])
async def test_channel(channel_id: int) -> Any:
    """手动测试渠道"""
    monitor = _get_health_monitor()
    result = await monitor.test_single_channel(channel_id)
    return result


@router.post("/api/gateway/channels/test-all", dependencies=[_require_api_key])
async def test_all_channels() -> Any:
    """批量测试所有渠道"""
    monitor = _get_health_monitor()
    results = await monitor.test_all_channels()
    return {"results": results, "total": len(results)}


@router.get("/api/gateway/dashboard", dependencies=[_require_api_key])
async def dashboard() -> Any:
    """
    网关 Dashboard

    返回成功率、延迟、费用等统计信息
    """
    cm = _get_channel_manager()
    cb = _get_circuit_breaker()

    channels = cm.list_all()
    enabled_count = len([ch for ch in channels if ch.status == 1])
    disabled_count = len([ch for ch in channels if ch.status != 1])

    # 获取所有模型
    all_models: set[str] = set()
    for ch in channels:
        all_models.update(ch.get_model_list())

    # 获取健康状态
    health_stats = cb.get_all_health()
    avg_success_rate = 0.0
    if health_stats:
        # rates = [h.total_requests - h.total_failures for h in health_stats.values()]
        total = sum(h.total_requests for h in health_stats.values())
        if total > 0:
            avg_success_rate = sum(
                (h.total_requests - h.total_failures) for h in health_stats.values()
            ) / total

    return {
        "channels": {
            "total": len(channels),
            "enabled": enabled_count,
            "disabled": disabled_count,
        },
        "models": {
            "total": len(all_models),
            "list": sorted(all_models),
        },
        "health": {
            "avg_success_rate": round(avg_success_rate, 4),
            "channels_tracked": len(health_stats),
        },
    }


# ── 健康检查端点（无需鉴权）──

@router.get("/health")
async def health_check() -> Any:
    """
    健康检查端点

    返回各 channel 状态、延迟、错误率。
    此端点不依赖 API Key 鉴权，供运维监控使用。
    """
    monitor = _get_health_monitor()
    return monitor.get_health_summary()
