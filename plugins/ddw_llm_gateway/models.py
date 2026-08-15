from datetime import datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class ModelRegistration(BaseModel):
    """已注册的 LLM 模型"""
    model_id: str = Field(..., description="唯一标识，如 deepseek-chat / qwen2.5:72b")
    provider: str = Field(...,
                          description="提供商：deepseek / minimax / mimo / ollama / vllm")  # noqa: E501
    display_name: str = Field(..., description="前端展示名")
    base_url: str = Field(..., description="上游 API 基础地址")
    api_key: str = Field(default="", description="上游 API Key（加密存储，响应中脱敏）")
    context_window: int = Field(default=128000, description="上下文窗口大小（tokens）")
    input_price_per_1m: float = Field(default=0.0, description="输入 token 价格（元/百万token）")  # noqa: E501
    output_price_per_1m: float = Field(
        default=0.0, description="输出 token 价格（元/百万token）")
    capabilities: list[str] = Field(
        default_factory=list, description="能力标签：chat/embedding/vision/code")
    priority: int = Field(default=100, description="路由优先级，数值越小越优先")
    weight: int = Field(default=1, description="同优先级内的负载均衡权重")
    is_local: bool = Field(default=False, description="是否为本地模型（Ollama/vLLM）")
    health_status: str = Field(
        default="unknown", description="健康状态：healthy/degraded/unhealthy/unknown")
    enabled: bool = Field(default=True, description="是否启用")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RouteRule(BaseModel):
    """路由规则"""
    rule_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    name: str = Field(..., description="规则名称，如 '代码生成路由'")
    scene: str = Field(default="default",
                       description="场景标识：default/code/chat/translate/sensitive")
    strategy: str = Field(default="priority",
                          description="路由策略：priority/cost/latency/fallback_only")
    model_chain: list[str] = Field(..., description="按优先级排列的 model_id 列表")
    max_retries: int = Field(default=3, description="最大重试次数（跨模型）")
    timeout_seconds: float = Field(default=30.0, description="单次请求超时")
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class UsageRecord(BaseModel):
    """Token 用量记录——兼容 ddw_llm_usage 插件的同名模型"""
    record_id: str = Field(default_factory=lambda: uuid4().hex[:16])
    api_key_id: str = Field(..., description="调用方 API Key ID")
    plugin_name: str = Field(default="ddw_llm_gateway", description="来源插件名")
    user_id: str = Field(default="", description="终端用户 ID（可选）")
    model_id: str = Field(..., description="实际调用的模型 ID")
    provider: str = Field(..., description="实际调用的提供商")
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    input_cost_cents: int = Field(default=0, description="输入费用（分）")
    output_cost_cents: int = Field(default=0, description="输出费用（分）")
    total_cost_cents: int = Field(default=0, description="总费用（分）")
    cache_hit: bool = Field(default=False, description="是否命中缓存")
    latency_ms: int = Field(default=0, description="上游响应延迟（毫秒）")
    status_code: int = Field(default=200)
    scene: str = Field(default="default")
    request_id: str = Field(default="", description="上游请求 ID")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class KeyCredential(BaseModel):
    """API Key 凭证"""
    key_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    key_prefix: str = Field(..., description="Key 前缀（用于日志脱敏展示），如 'sk-ddw-abc...xyz'")  # noqa: E501
    key_hash: str = Field(..., description="Key 的 SHA-256 哈希（存储用）")
    name: str = Field(..., description="Key 名称，如 '问渠学生端-生产'")
    plugin_name: str = Field(default="", description="绑定的插件名（空=全局）")
    user_id: str = Field(default="", description="绑定的用户 ID（空=插件级）")
    allowed_models: list[str] = Field(
        default_factory=list, description="可访问的模型列表（空=全部）")
    rate_limit_rpm: int = Field(default=60, description="每分钟请求限制")
    rate_limit_tpm: int = Field(default=100000, description="每分钟 token 限制")
    budget_cents: int = Field(default=0, description="总预算（分），0=不限")
    budget_period: str = Field(
        default="monthly", description="预算周期：daily/weekly/monthly/total")
    used_cents: int = Field(default=0, description="已使用金额（分）")
    status: str = Field(default="active", description="active/revoked/expired")
    expires_at: Optional[datetime] = Field(default=None, description="过期时间")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class BudgetPolicy(BaseModel):
    """预算策略"""
    policy_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    name: str = Field(..., description="策略名称")
    scope: str = Field(..., description="管控维度：key / plugin / user")
    scope_id: str = Field(..., description="对应的 key_id / plugin_name / user_id")
    limit_cents: int = Field(..., description="预算上限（分）")
    period: str = Field(default="monthly",
                        description="统计周期：daily/weekly/monthly/total")
    action_on_exceed: str = Field(
        default="block", description="超限动作：block / warn / notify")
    current_usage_cents: int = Field(default=0, description="当前周期已用（分）")
    reset_at: Optional[datetime] = Field(default=None, description="下次重置时间")
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
