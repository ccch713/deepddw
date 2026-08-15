import json
import time
import hashlib
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse

try:
    from .models import (
        ModelRegistration, RouteRule, UsageRecord, KeyCredential, BudgetPolicy
    )
    from .storage import Storage
except ImportError:
    from models import (
        ModelRegistration, RouteRule, UsageRecord, KeyCredential, BudgetPolicy
    )
    from storage import Storage

router = APIRouter()
storage = Storage()


def set_storage(s: Storage):
    """注入 storage 实例（测试用）"""
    global storage
    storage = s


# 辅助函数
def generate_key() -> str:
    """生成随机 API Key"""
    return f"sk-ddw-{uuid.uuid4().hex}"


def hash_key(key: str) -> str:
    """计算 API Key 的 SHA-256 哈希"""
    return hashlib.sha256(key.encode()).hexdigest()


def calculate_cost(model: ModelRegistration, usage: Dict[str, int]) -> tuple[int, int, int]:  # noqa: E501
    """计算费用（单位：分）"""
    input_tokens = usage.get("prompt_tokens", 0)
    output_tokens = usage.get("completion_tokens", 0)

    input_cost = int(input_tokens * model.input_price_per_1m / 1_000_000 * 100)
    output_cost = int(output_tokens * model.output_price_per_1m / 1_000_000 * 100)

    return input_cost, output_cost, input_cost + output_cost


async def call_upstream(model: ModelRegistration, request_data: Dict[str, Any],
                       timeout: float = 30.0) -> Dict[str, Any]:
    """调用上游 LLM 服务"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {model.api_key}"
    }

    # 构造请求数据
    upstream_data = request_data.copy()
    upstream_data["model"] = model.model_id

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{model.base_url}/chat/completions",
                json=upstream_data,
                headers=headers,
                timeout=timeout
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            raise Exception(f"Timeout calling {model.provider}")
        except httpx.HTTPStatusError as e:
            raise Exception(
                f"Upstream error {e.response.status_code}: {e.response.text}")
        except Exception as e:
            raise Exception(f"Failed to call {model.provider}: {str(e)}")


async def stream_upstream(model: ModelRegistration, request_data: Dict[str, Any],
                         timeout: float = 30.0):
    """流式调用上游 LLM 服务"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {model.api_key}"
    }

    upstream_data = request_data.copy()
    upstream_data["model"] = model.model_id
    upstream_data["stream"] = True

    async with httpx.AsyncClient() as client:
        try:
            async with client.stream(
                "POST",
                f"{model.base_url}/chat/completions",
                json=upstream_data,
                headers=headers,
                timeout=timeout
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        yield line + "\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"


def select_route(request_model: str) -> Optional[RouteRule]:
    """选择路由规则"""
    # 首先尝试匹配场景
    routes = storage.list_routes(scene=request_model)
    if routes:
        return routes[0]

    # 尝试匹配 model_id
    routes = storage.list_routes()
    for route in routes:
        if request_model in route.model_chain:
            return route

    # 默认路由
    default_routes = storage.list_routes(scene="default")
    return default_routes[0] if default_routes else None


def select_model(route: RouteRule, strategy: str = "priority") -> Optional[ModelRegistration]:  # noqa: E501
    """根据策略选择模型"""
    models = []
    for model_id in route.model_chain:
        model = storage.get_model(model_id)
        if model and model.enabled and model.health_status != "unhealthy":
            models.append(model)

    if not models:
        return None

    if strategy == "priority":
        # 按优先级排序
        models.sort(key=lambda m: m.priority)
        return models[0]
    elif strategy == "cost":
        # 按成本排序（输入+输出价格）
        models.sort(key=lambda m: m.input_price_per_1m + m.output_price_per_1m)
        return models[0]
    elif strategy == "latency":
        # 按延迟排序（这里简化，实际需要从健康状态获取）
        models.sort(key=lambda m: m.priority)  # 临时使用优先级
        return models[0]
    else:
        return models[0]


def check_budget(key_id: str, plugin_name: str, user_id: str) -> bool:
    """检查预算，返回 True 表示允许"""
    # 获取所有相关的预算策略
    policies = []
    policies.extend(storage.list_budgets(scope="key", scope_id=key_id))
    policies.extend(storage.list_budgets(scope="plugin", scope_id=plugin_name))
    if user_id:
        policies.extend(storage.list_budgets(scope="user", scope_id=user_id))

    for policy in policies:
        if not policy.enabled:
            continue
        if policy.current_usage_cents >= policy.limit_cents:
            if policy.action_on_exceed == "block":
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": {"message": f"Budget exceeded: {policy.name}", "type": "budget_exceeded"}}  # noqa: E501
                )
            elif policy.action_on_exceed == "warn":
                # 记录警告但允许继续
                pass
    return True


# 代理端点
@router.post("/v1/chat/completions")
async def chat_completions(request: Request):
    """统一 Chat Completions 代理"""
    # 解析请求体
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail={
                            "error": {"message": "Invalid JSON body"}})

    # 鉴权
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={
                            "error": {"message": "Missing API key"}})

    api_key = auth_header[7:]
    key_hash = hash_key(api_key)
    key_credential = storage.get_key_by_hash(key_hash)

    if not key_credential:
        raise HTTPException(status_code=401, detail={
                            "error": {"message": "Invalid API key"}})

    if key_credential.status != "active":
        raise HTTPException(status_code=401, detail={
                            "error": {"message": "API key revoked or expired"}})

    # 检查模型白名单
    request_model = body.get("model", "")
    if key_credential.allowed_models and request_model not in key_credential.allowed_models:  # noqa: E501
        raise HTTPException(status_code=403, detail={
                            "error": {"message": f"Model {request_model} not allowed"}})

    # 预算检查
    check_budget(key_credential.key_id, key_credential.plugin_name,
                 key_credential.user_id)

    # 路由决策
    route = select_route(request_model)
    if not route:
        raise HTTPException(status_code=404, detail={
                            "error": {"message": f"No route found for model {request_model}"}})  # noqa: E501

    # 选择模型
    model = select_model(route, route.strategy)
    if not model:
        raise HTTPException(status_code=503, detail={
                            "error": {"message": "No available models"}})

    # 调用上游
    start_time = time.time()
    errors = []

    # 尝试 model_chain 中的模型
    for model_id in route.model_chain:
        current_model = storage.get_model(model_id)
        if not current_model or not current_model.enabled:
            continue
        if current_model.health_status == "unhealthy":
            errors.append(f"{model_id}: unhealthy, skip")
            continue

        try:
            if body.get("stream", False):
                # 流式响应
                async def generate():
                    async for chunk in stream_upstream(current_model, body, route.timeout_seconds):  # noqa: E501
                        yield chunk

                response = StreamingResponse(
                    generate(),
                    media_type="text/event-stream",
                    headers={
                        "x-llm-provider": current_model.provider,
                        "x-llm-model": current_model.model_id,
                        "x-llm-cost": "0",  # 流式结束时计算
                        "x-llm-latency": "0"
                    }
                )

                # 记录用量（简化版，实际需要在流式结束时记录）
                usage_record = UsageRecord(
                    api_key_id=key_credential.key_id,
                    model_id=current_model.model_id,
                    provider=current_model.provider,
                    scene=route.scene
                )
                storage.create_usage_record(usage_record)

                return response
            else:
                # 非流式响应
                upstream_response = await call_upstream(current_model, body, route.timeout_seconds)  # noqa: E501

                # 计算延迟
                latency_ms = int((time.time() - start_time) * 1000)

                # 计算费用
                usage = upstream_response.get("usage", {})
                input_cost, output_cost, total_cost = calculate_cost(
                    current_model, usage)

                # 记录用量
                usage_record = UsageRecord(
                    api_key_id=key_credential.key_id,
                    model_id=current_model.model_id,
                    provider=current_model.provider,
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                    total_tokens=usage.get("total_tokens", 0),
                    input_cost_cents=input_cost,
                    output_cost_cents=output_cost,
                    total_cost_cents=total_cost,
                    latency_ms=latency_ms,
                    status_code=200,
                    scene=route.scene
                )
                storage.create_usage_record(usage_record)

                # 返回响应
                response_data = upstream_response.copy()
                response_data["model"] = current_model.model_id

                return JSONResponse(
                    content=response_data,
                    headers={
                        "x-llm-provider": current_model.provider,
                        "x-llm-model": current_model.model_id,
                        "x-llm-cost": str(total_cost),
                        "x-llm-latency": str(latency_ms)
                    }
                )

        except Exception as e:
            errors.append(f"{model_id}: {str(e)}")
            # 记录审计日志
            storage.create_audit_log(
                action="request.fallback",
                actor_key_id=key_credential.key_id,
                target_type="model",
                target_id=model_id,
                detail=str(e)
            )
            continue

    # 所有模型都失败
    raise HTTPException(
        status_code=503,
        detail={"error": {
            "message": f"All providers failed: {'; '.join(errors)}", "type": "all_providers_failed"}}  # noqa: E501
    )


@router.get("/v1/models")
async def list_models():
    """列出可用模型（OpenAI 兼容格式）"""
    models = storage.list_models(enabled=True)

    data = []
    for model in models:
        data.append({
            "id": model.model_id,
            "object": "model",
            "created": int(model.created_at.timestamp()),
            "owned_by": model.provider,
            "permission": [],
            "root": model.model_id,
            "parent": None
        })

    return {"object": "list", "data": data}


# Admin 端点 - 模型管理
@router.post("/admin/models")
async def create_model(model: ModelRegistration):
    """注册新模型"""
    existing = storage.get_model(model.model_id)
    if existing:
        raise HTTPException(status_code=409, detail={
                            "error": {"message": f"Model {model.model_id} already exists"}})  # noqa: E501

    created = storage.create_model(model)
    storage.create_audit_log(
        action="model.create",
        target_type="model",
        target_id=model.model_id,
        detail=json.dumps(model.model_dump(), default=str)
    )
    return created


@router.get("/admin/models")
async def list_admin_models(enabled: Optional[bool] = None, provider: Optional[str] = None):  # noqa: E501
    """列出所有模型"""
    return storage.list_models(enabled=enabled, provider=provider)


@router.get("/admin/models/{model_id}")
async def get_model(model_id: str):
    """查询单个模型"""
    model = storage.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail={
                            "error": {"message": f"Model {model_id} not found"}})
    return model


@router.put("/admin/models/{model_id}")
async def update_model(model_id: str, updates: Dict[str, Any]):
    """更新模型配置"""
    model = storage.update_model(model_id, updates)
    if not model:
        raise HTTPException(status_code=404, detail={
                            "error": {"message": f"Model {model_id} not found"}})

    storage.create_audit_log(
        action="model.update",
        target_type="model",
        target_id=model_id,
        detail=json.dumps(updates, default=str)
    )
    return model


@router.delete("/admin/models/{model_id}")
async def delete_model(model_id: str):
    """删除模型"""
    if not storage.delete_model(model_id):
        raise HTTPException(status_code=404, detail={
                            "error": {"message": f"Model {model_id} not found"}})

    storage.create_audit_log(
        action="model.delete",
        target_type="model",
        target_id=model_id
    )
    return {"ok": True}


# Admin 端点 - 路由管理
@router.post("/admin/routes")
async def create_route(route: RouteRule):
    """创建路由规则"""
    created = storage.create_route(route)
    storage.create_audit_log(
        action="route.create",
        target_type="route",
        target_id=route.rule_id,
        detail=json.dumps(route.model_dump(), default=str)
    )
    return created


@router.get("/admin/routes")
async def list_routes(scene: Optional[str] = None):
    """列出路由规则"""
    return storage.list_routes(scene=scene)


@router.get("/admin/routes/{rule_id}")
async def get_route(rule_id: str):
    """查询单条规则"""
    route = storage.get_route(rule_id)
    if not route:
        raise HTTPException(status_code=404, detail={
                            "error": {"message": f"Route {rule_id} not found"}})
    return route


@router.put("/admin/routes/{rule_id}")
async def update_route(rule_id: str, updates: Dict[str, Any]):
    """更新路由规则"""
    route = storage.update_route(rule_id, updates)
    if not route:
        raise HTTPException(status_code=404, detail={
                            "error": {"message": f"Route {rule_id} not found"}})

    storage.create_audit_log(
        action="route.update",
        target_type="route",
        target_id=rule_id,
        detail=json.dumps(updates, default=str)
    )
    return route


@router.delete("/admin/routes/{rule_id}")
async def delete_route(rule_id: str):
    """删除路由规则"""
    if not storage.delete_route(rule_id):
        raise HTTPException(status_code=404, detail={
                            "error": {"message": f"Route {rule_id} not found"}})

    storage.create_audit_log(
        action="route.delete",
        target_type="route",
        target_id=rule_id
    )
    return {"ok": True}


# Admin 端点 - Key 管理
@router.post("/admin/keys")
async def create_key(key_data: Dict[str, Any]):
    """创建 API Key"""
    # 生成 Key
    api_key = generate_key()
    key_hash = hash_key(api_key)
    key_prefix = f"{api_key[:10]}...{api_key[-4:]}"

    key_credential = KeyCredential(
        key_prefix=key_prefix,
        key_hash=key_hash,
        **key_data
    )

    created = storage.create_key(key_credential)
    storage.create_audit_log(
        action="key.create",
        target_type="key",
        target_id=created.key_id,
        detail=f"Created key for {key_data.get('name', 'unknown')}"
    )

    # 返回时包含明文 key（仅此一次）
    result = created.model_dump()
    result["api_key"] = api_key
    return result


@router.get("/admin/keys")
async def list_keys(plugin_name: Optional[str] = None, status: Optional[str] = None):
    """列出所有 Key"""
    return storage.list_keys(plugin_name=plugin_name, status=status)


@router.get("/admin/keys/{key_id}")
async def get_key(key_id: str):
    """查询单个 Key"""
    key = storage.get_key(key_id)
    if not key:
        raise HTTPException(status_code=404, detail={
                            "error": {"message": f"Key {key_id} not found"}})
    return key


@router.put("/admin/keys/{key_id}")
async def update_key(key_id: str, updates: Dict[str, Any]):
    """更新 Key 配置"""
    key = storage.update_key(key_id, updates)
    if not key:
        raise HTTPException(status_code=404, detail={
                            "error": {"message": f"Key {key_id} not found"}})

    storage.create_audit_log(
        action="key.update",
        target_type="key",
        target_id=key_id,
        detail=json.dumps(updates, default=str)
    )
    return key


@router.delete("/admin/keys/{key_id}")
async def delete_key(key_id: str):
    """吊销 Key"""
    if not storage.delete_key(key_id):
        raise HTTPException(status_code=404, detail={
                            "error": {"message": f"Key {key_id} not found"}})

    storage.create_audit_log(
        action="key.delete",
        target_type="key",
        target_id=key_id
    )
    return {"ok": True}


# Admin 端点 - 预算管理
@router.post("/admin/budgets")
async def create_budget(policy: BudgetPolicy):
    """创建预算策略"""
    created = storage.create_budget(policy)
    storage.create_audit_log(
        action="budget.create",
        target_type="budget",
        target_id=policy.policy_id,
        detail=json.dumps(policy.model_dump(), default=str)
    )
    return created


@router.get("/admin/budgets")
async def list_budgets(scope: Optional[str] = None, scope_id: Optional[str] = None):
    """列出预算策略"""
    return storage.list_budgets(scope=scope, scope_id=scope_id)


@router.get("/admin/budgets/{policy_id}")
async def get_budget(policy_id: str):
    """查询单条策略"""
    policy = storage.get_budget(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail={
                            "error": {"message": f"Budget {policy_id} not found"}})
    return policy


@router.put("/admin/budgets/{policy_id}")
async def update_budget(policy_id: str, updates: Dict[str, Any]):
    """更新预算策略"""
    policy = storage.update_budget(policy_id, updates)
    if not policy:
        raise HTTPException(status_code=404, detail={
                            "error": {"message": f"Budget {policy_id} not found"}})

    storage.create_audit_log(
        action="budget.update",
        target_type="budget",
        target_id=policy_id,
        detail=json.dumps(updates, default=str)
    )
    return policy


@router.delete("/admin/budgets/{policy_id}")
async def delete_budget(policy_id: str):
    """删除预算策略"""
    if not storage.delete_budget(policy_id):
        raise HTTPException(status_code=404, detail={
                            "error": {"message": f"Budget {policy_id} not found"}})

    storage.create_audit_log(
        action="budget.delete",
        target_type="budget",
        target_id=policy_id
    )
    return {"ok": True}


# Admin 端点 - 审计日志
@router.get("/admin/audit")
async def get_audit_logs(action: Optional[str] = None, limit: int = 100, offset: int = 0):  # noqa: E501
    """查询审计日志"""
    return storage.get_audit_logs(action=action, limit=limit, offset=offset)


# 辅助端点
@router.get("/health")
async def health_check():
    """健康检查"""
    models = storage.list_models(enabled=True)
    statuses = {}
    for model in models:
        health = storage.get_health_status(model.model_id)
        statuses[model.model_id] = {
            "status": health["status"] if health else "unknown",
            "latency_ms": health["latency_ms"] if health else 0
        }

    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "models": statuses
    }


@router.get("/ready")
async def ready_check():
    """就绪检查"""
    return {"status": "ready"}
