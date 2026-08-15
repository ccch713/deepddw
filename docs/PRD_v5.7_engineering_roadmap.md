# DDW AI Hub Platform v5.7 — 工程补强路线图

> **版本**：v5.7 MASTER（基于 v5.6 + One API 源码分析深度适配 + SDK 基线修复）
> **日期**：2026-07-13
> **基于**：v5.6_MASTER.md + DeepSeek V4 Pro 架构分析 + MiMo V2.5 适配蓝图 + 实际代码审计
> **文档性质**：工程补强路线图（S27-S32），与 v5.6 (S1-S26) 叠加使用
> **标记说明**：`[v5.7新增]` = 本版新增内容 | `[v5.7修复]` = 基于代码审计发现问题的修复 | 无标记 = 沿用 v5.6

**v5.7 核心变更**：
1. **LLM Gateway 插件完整规格**（§27）—— ddw-llm-gateway 插件从 One API 51 种渠道类型完整迁移
2. **Token Manager SDK 基线修复**（§28）—— 消除自定义基类，强制继承 SDK PluginBase/PluginState
3. **插件开发规范硬约束**（§29）—— 从建议升级为强制：继承、测试、manifest、Git 仓
4. **One API 设计模式 Python 迁移清单**（§30）—— 6 大模式逐项迁移方案
5. **安全补强清单**（§31）—— 6 项 P0 安全漏洞修复
6. **性能补强清单**（§32）—— 直传模式、连接池、Token 近似计算

---

## 目录

27. [⭐ LLM Gateway 插件 (ddw-llm-gateway) 完整规格](#27-llm-gateway-插件-ddw-llm-gateway-完整规格)
28. [⭐ Token Manager 插件 SDK 基线修复](#28-token-manager-插件-sdk-基线修复)
29. [⭐ 插件开发规范硬约束](#29-插件开发规范硬约束)
30. [One API 设计模式 Python 迁移清单](#30-one-api-设计模式-python-迁移清单)
31. [安全补强清单](#31-安全补强清单)
32. [性能补强清单](#32-性能补强清单)
33. [开发里程碑与排期](#33-开发里程碑与排期)
34. [变更记录](#34-变更记录)
35. [⭐ 质量评估（DeepSeek V4 Pro 视角）](#35-质量评估deepseek-v4-pro-视角)

---

## 27. LLM Gateway 插件 (ddw-llm-gateway) 完整规格

> **背景**：One API 源码分析揭示了一个成熟的 LLM 网关架构——51 种渠道类型、19 种 API 适配器、优先级+随机负载均衡、失败重试+自动禁用。DDW 需要将这些能力以插件形式复现，并与现有 ddw-token-manager 深度集成。

### 27.1 插件定位

```
ddw-llm-gateway 插件 = One API relay/ + middleware/ + monitor/ 的 Python/FastAPI 适配
                        ↓
核心职责：
  1. 统一 LLM 请求入口（OpenAI 兼容格式）
  2. 51 种渠道类型 YAML 配置化
  3. 优先级+随机+权重负载均衡
  4. 失败重试 + 渠道自动禁用/启用
  5. 流式 SSE 透传
  6. 与 ddw-token-manager 预消费/后消费集成
```

### 27.2 插件 Manifest

```yaml
name: ddw-llm-gateway
version: 1.0.0
engine: ">=0.1.0"
description: "LLM 统一网关插件 — 渠道管理、负载均衡、失败重试、流式转发"
category: infrastructure
author: "DDW AI Hub"
license: MIT

dependencies:
  plugins:
    ddw-core: ">=0.1.0"
    ddw-token-manager: ">=0.1.0"    # 预消费/后消费集成

permissions:
  - "database:channels"
  - "database:channel_groups"
  - "api:llm:relay"
  - "api:llm:admin"
  - "event:channel.health"

config_schema:
  default_provider:
    type: string
    default: "minimax"
    description: "默认 LLM Provider"
  retry_max_attempts:
    type: integer
    default: 3
    description: "最大重试次数"
  retry_backoff_base:
    type: float
    default: 1.0
    description: "重试退避基数（秒）"
  channel_disable_threshold:
    type: float
    default: 0.5
    description: "渠道自动禁用成功率阈值"
  channel_test_interval:
    type: integer
    default: 300
    description: "渠道自动测试间隔（秒）"
  stream_buffer_size:
    type: integer
    default: 1024
    description: "SSE 流式缓冲区大小（字节）"

isolation: inline

ecosystem:
  depends_on: ["ddw-core", "ddw-token-manager"]
  enhances: ["ddw-ai-engine"]
  category: "infrastructure"
  tags: ["llm", "gateway", "relay", "routing", "load-balancing"]

obfuscation: disabled
```

### 27.3 渠道管理（Channel Manager）

**映射源**：One API `model/channel.go` + `model/channeltype/`

#### 27.3.1 渠道类型枚举（51 种）

```python
# ddw_llm_gateway/channel_types.py

from enum import Enum

class ChannelType(int, Enum):
    """One API 51 种渠道类型 → DDW 映射
    
    映射规则:
    - 原生 OpenAI 兼容: 直接使用 openai SDK
    - 私有 API: 需要适配器转换
    - 开源框架: 本地部署渠道
    """
    # ── 云端 LLM（OpenAI 兼容）──
    OPENAI = 1                    # OpenAI GPT 系列
    AZURE_OPENAI = 3              # Azure OpenAI
    ANTHROPIC = 8                 # Claude 系列
    BAIDU = 14                    # 百度文心一言
    ZHIPU = 15                    # 智谱 GLM
    DEEPSEEK = 24                 # DeepSeek V4 Pro
    MINIMAX = 25                  # MiniMax M3
    MISTRAL = 28                  # Mistral AI
    GROQ = 29                     # Groq
    TOGETHER = 30                 # Together AI
    OPENROUTER = 31               # OpenRouter
    DASHSCOPE = 42                # 阿里通义千问
    VOLCENGINE = 43               # 字节豆包
    SILICONFLOW = 48              # 硅基流动
    
    # ── 国内云厂商 ──
    TENCENT = 23                  # 腾讯混元
    HUNYUAN = 44                  # 混元独立
    XUNFEI = 16                   # 讯飞星火
    BAICHUAN = 26                 # 百川
    SENSETIME = 34                # 商汤
    YI = 38                       # 零一万物
    
    # ── 开源框架 ──
    OLLAMA = 11                   # Ollama 本地
    VLLM = 45                     # vLLM
    LLAMACPP = 46                 # llama.cpp
    CUSTOM = 100                  # 自定义
    
    # ... 共 51 种（完整列表见附录 E）
```

#### 27.3.2 渠道配置 YAML 化

```yaml
# config/channels.yaml — 渠道配置文件
# 映射: One API model/channel.go + model/channel_cache.go

channels:
  - id: 1
    name: "minimax-m3-primary"
    type: 25                    # ChannelType.MINIMAX
    base_url: "https://api.minimax.chat"
    api_keys:
      - "sk-${MINIMAX_KEY_1}"
      - "sk-${MINIMAX_KEY_2}"  # 多 Key 轮转
    models:
      - "MiniMax-Text-01"
      - "MiniMax-Text-01-40k"
    status: 1                   # 1=Enabled
    priority: 10                # 高优先级
    weight: 100                 # 权重
    group: "default"
    config:
      temperature: 0.7
      top_p: 0.9
      max_tokens: 4096

  - id: 2
    name: "deepseek-v4-pro"
    type: 24                    # ChannelType.DEEPSEEK
    base_url: "https://api.deepseek.com"
    api_keys:
      - "sk-${DEEPSEEK_KEY}"
    models:
      - "deepseek-chat"
      - "deepseek-reasoner"
    status: 1
    priority: 5
    weight: 80
    group: "default"

  - id: 3
    name: "ollama-local"
    type: 11                    # ChannelType.OLLAMA
    base_url: "http://localhost:11434"
    api_keys:
      - "ollama"                # Ollama 不需要真实 Key
    models:
      - "deepseek-coder-v2:16b-lite-instruct-q4_K_M"
      - "qwen2.5:14b"
    status: 1
    priority: 1
    weight: 50
    group: "default"
```

#### 27.3.3 渠道数据模型

```python
# ddw_llm_gateway/models.py

from sqlalchemy import Column, Integer, String, Float, Text, JSON, Boolean
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

class Channel(Base):
    """渠道表 — 映射 One API model/channel.go:Channel (L20-41)"""
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(Integer, default=0, nullable=False)          # ChannelType 枚举值
    name = Column(String(255), index=True, nullable=False)
    key = Column(Text, nullable=False)                          # API 密钥（加密存储）
    status = Column(Integer, default=1, nullable=False)        # 0=Unknown 1=Enabled 2=ManualDisabled 3=AutoDisabled
    weight = Column(Integer, default=0, nullable=False)        # 负载均衡权重
    priority = Column(Integer, default=0, nullable=False)      # 优先级（越大越高）
    base_url = Column(String(255), default="", nullable=False)
    balance = Column(Float, default=0.0)                        # USD 余额
    models = Column(Text, default="", nullable=False)           # 逗号分隔的模型列表
    model_mapping = Column(Text, default="", nullable=False)    # 模型名映射 JSON
    group = Column(String(32), default="default", nullable=False)
    used_quota = Column(Integer, default=0, nullable=False)
    response_time = Column(Integer, default=0)                  # 响应时间（毫秒）
    test_time = Column(Integer, default=0)                      # 最后测试时间戳
    config = Column(JSON, default=dict)                         # 渠道特定配置
    system_prompt = Column(Text, default="")
    created_time = Column(Integer, default=0)
    
    # ── 健康监控字段 ──
    success_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    consecutive_failures = Column(Integer, default=0)
    last_success_at = Column(Integer, default=0)
    last_failure_at = Column(Integer, default=0)
    auto_disabled_at = Column(Integer, default=0)               # 自动禁用时间
    retest_interval = Column(Integer, default=300)              # 重测间隔（秒）
```

### 27.4 负载均衡引擎（Load Balancer）

**映射源**：One API `middleware/distributor.go` + `model/cache.go:CacheGetRandomSatisfiedChannel()`

```python
# ddw_llm_gateway/load_balancer.py

from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Optional

@dataclass
class ChannelCandidate:
    """渠道候选（从缓存中筛选出的合格渠道）"""
    id: int
    name: str
    priority: int
    weight: int
    response_time: int      # 毫秒
    balance: float
    success_rate: float     # 0.0 ~ 1.0

class LoadBalancer:
    """
    渠道负载均衡器
    
    三阶段筛选:
    1. 按优先级分组（priority 从高到低）
    2. 同优先级内按加权随机（weight 权重）
    3. 成功率 > 阈值 + 余额 > 0 过滤
    
    映射: middleware/distributor.go:Distribute()
          model/cache.go:CacheGetRandomSatisfiedChannel()
    """
    
    def __init__(self, success_rate_threshold: float = 0.5):
        self._threshold = success_rate_threshold
    
    def select(
        self,
        candidates: list[ChannelCandidate],
        model: str = "",
    ) -> Optional[ChannelCandidate]:
        """
        从候选列表中选择一个渠道
        
        Args:
            candidates: 合格渠道列表
            model: 请求的模型名（用于过滤支持该模型的渠道）
        
        Returns:
            选中的渠道，或 None
        """
        # Step 1: 过滤
        eligible = [
            c for c in candidates
            if (c.success_rate >= self._threshold
                and (c.balance > 0 or c.balance < 0)  # balance < 0 = 无限额度
                and c.id > 0)
        ]
        
        if not eligible:
            return None
        
        # Step 2: 按优先级分组
        max_priority = max(c.priority for c in eligible)
        top_tier = [c for c in eligible if c.priority == max_priority]
        
        # Step 3: 加权随机选择
        if len(top_tier) == 1:
            return top_tier[0]
        
        weights = [max(c.weight, 1) for c in top_tier]
        return random.choices(top_tier, weights=weights, k=1)[0]
```

### 27.5 失败重试与自动禁用（Retry + Circuit Breaker）

**映射源**：One API `controller/relay.go` 重试循环 + `monitor/monitor.go` 渠道自动禁用

```python
# ddw_llm_gateway/circuit_breaker.py

from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

class ChannelStatus(int, Enum):
    """渠道状态 — 映射 One API model/channel.go Status"""
    UNKNOWN = 0
    ENABLED = 1
    MANUAL_DISABLED = 2
    AUTO_DISABLED = 3

@dataclass
class ChannelHealth:
    """渠道健康状态追踪"""
    channel_id: int
    status: ChannelStatus = ChannelStatus.ENABLED
    consecutive_failures: int = 0
    total_requests: int = 0
    total_failures: int = 0
    last_success_at: float = 0.0
    last_failure_at: float = 0.0
    auto_disabled_at: float = 0.0

class CircuitBreaker:
    """
    渠道断路器 — 映射 One API monitor/monitor.go
    
    规则:
    1. 连续失败 ≥ disable_threshold → 自动禁用渠道（AUTO_DISABLED）
    2. 禁用后每 retest_interval 秒自动测试一次
    3. 测试成功 → 恢复为 ENABLED
    4. 成功率 = success / (success + failure)，低于阈值则降级
    
    对应 One API:
    - monitor.go:Emit() → 失败计数
    - controller/channel-test.go:AutomaticallyTestChannels() → 定时测试
    """
    
    def __init__(
        self,
        disable_threshold: int = 5,
        retest_interval: int = 300,
        success_rate_threshold: float = 0.5,
    ):
        self._disable_threshold = disable_threshold
        self._retest_interval = retest_interval
        self._success_rate_threshold = success_rate_threshold
        self._health: dict[int, ChannelHealth] = {}
    
    def record_success(self, channel_id: int) -> None:
        """记录成功"""
        h = self._get_or_create(channel_id)
        h.consecutive_failures = 0
        h.total_requests += 1
        h.last_success_at = time.time()
        
        # 如果之前被自动禁用，恢复
        if h.status == ChannelStatus.AUTO_DISABLED:
            h.status = ChannelStatus.ENABLED
            logger.info("渠道 %d 恢复为启用状态", channel_id)
    
    def record_failure(self, channel_id: int) -> None:
        """记录失败"""
        h = self._get_or_create(channel_id)
        h.consecutive_failures += 1
        h.total_requests += 1
        h.total_failures += 1
        h.last_failure_at = time.time()
        
        # 连续失败达到阈值 → 自动禁用
        if h.consecutive_failures >= self._disable_threshold:
            h.status = ChannelStatus.AUTO_DISABLED
            h.auto_disabled_at = time.time()
            logger.warning(
                "渠道 %d 因连续 %d 次失败自动禁用",
                channel_id, h.consecutive_failures
            )
    
    def should_retry(self, channel_id: int) -> bool:
        """检查渠道是否可以重试"""
        h = self._get_or_create(channel_id)
        return h.status == ChannelStatus.ENABLED
    
    def should_retest(self, channel_id: int) -> bool:
        """检查禁用渠道是否到了重测时间"""
        h = self._get_or_create(channel_id)
        if h.status != ChannelStatus.AUTO_DISABLED:
            return False
        if h.auto_disabled_at == 0:
            return False
        return (time.time() - h.auto_disabled_at) >= self._retest_interval
    
    def get_success_rate(self, channel_id: int) -> float:
        """获取成功率"""
        h = self._get_or_create(channel_id)
        if h.total_requests == 0:
            return 1.0
        return (h.total_requests - h.total_failures) / h.total_requests
    
    def _get_or_create(self, channel_id: int) -> ChannelHealth:
        if channel_id not in self._health:
            self._health[channel_id] = ChannelHealth(channel_id=channel_id)
        return self._health[channel_id]
```

### 27.6 流式 SSE 转发

**映射源**：One API `relay/controller/text.go` Stream 处理

```python
# ddw_llm_gateway/stream_relay.py

from __future__ import annotations
import json
import logging
from typing import AsyncGenerator

from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

class StreamRelay:
    """
    流式 SSE 转发器
    
    映射: relay/controller/text.go — StreamResponse 处理
    核心: 接收上游 SSE → 解析 → 注入 Token 计量 → 转发给下游
    
    SSE 格式:
    data: {"id":"chatcmpl-xxx","choices":[{"delta":{"content":"Hello"}}]}
    data: [DONE]
    """
    
    def __init__(self, buffer_size: int = 1024):
        self._buffer_size = buffer_size
    
    async def relay_stream(
        self,
        upstream_stream: AsyncGenerator[str, None],
        on_chunk: callable = None,
    ) -> StreamingResponse:
        """
        将上游流式响应转发为 SSE 响应
        
        Args:
            upstream_stream: 上游 LLM 的 SSE 流
            on_chunk: 每个 chunk 的回调（用于 Token 计量）
        
        Returns:
            FastAPI StreamingResponse
        """
        async def generate():
            total_tokens = 0
            async for chunk in upstream_stream:
                if chunk.startswith("data: "):
                    data_str = chunk[6:].strip()
                    if data_str == "[DONE]":
                        yield f"data: [DONE]\n\n"
                        break
                    
                    try:
                        data = json.loads(data_str)
                        # 提取 usage 信息（最后一个 chunk）
                        if "usage" in data:
                            total_tokens = data["usage"].get("total_tokens", 0)
                        # 回调：用于 Token 计量
                        if on_chunk:
                            on_chunk(data)
                        yield f"data: {data_str}\n\n"
                    except json.JSONDecodeError:
                        yield f"data: {data_str}\n\n"
                else:
                    yield f"{chunk}\n"
        
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    
    async def relay_stream_with_usage(
        self,
        upstream_stream: AsyncGenerator[str, None],
        token_manager=None,
        channel_id: int = 0,
        model: str = "",
        user_id: int = 0,
    ) -> StreamingResponse:
        """
        带 Token 计量的流式转发
        
        流式结束后，根据最后一个 chunk 的 usage 信息
        调用 token_manager.post_consume() 进行后置计费。
        """
        collected_usage = {}
        
        def on_chunk(data):
            if "usage" in data:
                collected_usage.update(data["usage"])
        
        response = await self.relay_stream(upstream_stream, on_chunk)
        
        # 后置计费（流结束后）
        if token_manager and collected_usage:
            await token_manager.post_consume(
                channel_id=channel_id,
                model=model,
                user_id=user_id,
                prompt_tokens=collected_usage.get("prompt_tokens", 0),
                completion_tokens=collected_usage.get("completion_tokens", 0),
            )
        
        return response
```

### 27.7 与 ddw-token-manager 集成接口

**映射源**：One API `relay/controller/text.go:preConsumeQuota()` + `postConsumeQuota()`

```python
# ddw_llm_gateway/quota_integration.py

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class PreConsumeResult:
    """预消费结果"""
    allowed: bool
    remaining_quota: int
    estimated_cost: float     # 预估成本（含峰时倍率）
    subscription_id: Optional[int] = None
    error_message: str = ""

class QuotaIntegration:
    """
    与 ddw-token-manager 的预消费/后消费集成
    
    映射: One API relay/controller/helper.go:preConsumeQuota (L97-141)
    
    流程:
    1. pre_consume: 请求前检查额度 → 预扣 → 返回预估成本
    2. post_consume: 请求后按实际消耗结算 → 多退少补
    """
    
    def __init__(self, token_manager=None):
        self._token_manager = token_manager
    
    async def pre_consume(
        self,
        user_id: int,
        model: str,
        estimated_tokens: int = 0,
    ) -> PreConsumeResult:
        """
        预消费：检查额度 + 预扣
        
        对应 One API: relay/controller/helper.go:preConsumeQuota()
        """
        if not self._token_manager:
            return PreConsumeResult(allowed=True, remaining_quota=-1, estimated_cost=0)
        
        try:
            # 调用 token_manager 检查额度
            quota_info = await self._token_manager.check_quota(user_id, model)
            if not quota_info["allowed"]:
                return PreConsumeResult(
                    allowed=False,
                    remaining_quota=quota_info.get("remaining", 0),
                    estimated_cost=0,
                    error_message=quota_info.get("error", "额度不足"),
                )
            
            # 预扣（乐观锁）
            estimated_cost = await self._token_manager.estimate_cost(
                model=model, tokens=estimated_tokens
            )
            await self._token_manager.deduct_quota(user_id, estimated_cost)
            
            return PreConsumeResult(
                allowed=True,
                remaining_quota=quota_info.get("remaining", 0) - int(estimated_cost),
                estimated_cost=estimated_cost,
                subscription_id=quota_info.get("subscription_id"),
            )
        except Exception as e:
            logger.error("预消费失败: %s", e)
            return PreConsumeResult(
                allowed=False, remaining_quota=0, estimated_cost=0,
                error_message=str(e),
            )
    
    async def post_consume(
        self,
        user_id: int,
        channel_id: int,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        subscription_id: Optional[int] = None,
    ) -> None:
        """
        后置计费：按实际消耗结算差额
        
        对应 One API: relay/controller/helper.go:postConsumeQuota()
        
        差额 = 实际消耗 - 预扣额度
        差额 > 0 → 补扣
        差额 < 0 → 退还
        """
        if not self._token_manager:
            return
        
        try:
            actual_cost = await self._token_manager.calculate_actual_cost(
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                subscription_id=subscription_id,
            )
            
            # 记录消费日志
            await self._token_manager.log_consume(
                user_id=user_id,
                channel_id=channel_id,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                quota_cost=actual_cost,
            )
            
            # 差额结算
            await self._token_manager.settle_quota(user_id, actual_cost)
            
        except Exception as e:
            logger.error("后置计费失败: %s", e)
```

### 27.8 渠道健康监控后台任务

**映射源**：One API `controller/channel-test.go:AutomaticallyTestChannels()`

```python
# ddw_llm_gateway/health_monitor.py

import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

class ChannelHealthMonitor:
    """
    渠道健康监控 — 定时测试 + 自动禁用/启用
    
    映射: controller/channel-test.go:AutomaticallyTestChannels()
          (goroutine, 每 N 秒扫描一次)
    
    流程:
    1. 每 retest_interval 秒扫描所有渠道
    2. AUTO_DISABLED 渠道 → 发送测试请求
    3. 测试成功 → 恢复 ENABLED
    4. 测试失败 → 保持 AUTO_DISABLED，重置计时
    5. ENABLED 渠道连续失败 → 自动禁用
    """
    
    def __init__(
        self,
        channel_manager=None,
        circuit_breaker=None,
        retest_interval: int = 300,
    ):
        self._channel_manager = channel_manager
        self._circuit_breaker = circuit_breaker
        self._retest_interval = retest_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self) -> None:
        """启动后台监控"""
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("渠道健康监控已启动，间隔 %d 秒", self._retest_interval)
    
    async def stop(self) -> None:
        """停止后台监控"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("渠道健康监控已停止")
    
    async def _monitor_loop(self) -> None:
        """监控主循环"""
        while self._running:
            try:
                await self._scan_channels()
            except Exception as e:
                logger.error("渠道扫描异常: %s", e)
            await asyncio.sleep(self._retest_interval)
    
    async def _scan_channels(self) -> None:
        """扫描所有渠道，测试需要重测的"""
        if not self._channel_manager or not self._circuit_breaker:
            return
        
        channels = await self._channel_manager.list_all()
        for channel in channels:
            if self._circuit_breaker.should_retest(channel.id):
                await self._test_channel(channel)
    
    async def _test_channel(self, channel) -> None:
        """测试单个渠道"""
        try:
            # 发送简单的测试请求
            # 实际实现调用 LLM API 的 /models 端点
            success = await self._ping_channel(channel)
            if success:
                self._circuit_breaker.record_success(channel.id)
                logger.info("渠道 %s (%d) 测试通过，恢复启用", channel.name, channel.id)
            else:
                self._circuit_breaker.record_failure(channel.id)
                logger.warning("渠道 %s (%d) 测试失败", channel.name, channel.id)
        except Exception as e:
            self._circuit_breaker.record_failure(channel.id)
            logger.error("渠道 %s (%d) 测试异常: %s", channel.name, channel.id, e)
    
    async def _ping_channel(self, channel) -> bool:
        """发送轻量级 ping 测试"""
        # 实际实现：发送 GET /v1/models 或最小 POST 请求
        # 这里返回 True 表示占位
        return True
```

### 27.9 API 端点

| 端点 | 方法 | 说明 | 映射源 |
|:-----|:-----|:-----|:-------|
| `/v1/chat/completions` | POST | Chat Completion 转发（OpenAI 兼容） | `router/relay.go` |
| `/v1/completions` | POST | Text Completion 转发 | `router/relay.go` |
| `/v1/embeddings` | POST | Embedding 转发 | `router/relay.go` |
| `/v1/images/generations` | POST | 图像生成转发 | `router/relay.go` |
| `/v1/audio/transcriptions` | POST | 语音转文字转发 | `router/relay.go` |
| `/v1/models` | GET | 可用模型列表 | `controller/model.go` |
| `/api/gateway/channels` | GET | 渠道列表（管理） | `controller/channel.go` |
| `/api/gateway/channels` | POST | 创建渠道 | `controller/channel.go` |
| `/api/gateway/channels/{id}` | PUT | 更新渠道 | `controller/channel.go` |
| `/api/gateway/channels/{id}` | DELETE | 删除渠道 | `controller/channel.go` |
| `/api/gateway/channels/{id}/test` | POST | 手动测试渠道 | `controller/channel-test.go` |
| `/api/gateway/channels/test-all` | POST | 批量测试所有渠道 | `controller/channel-test.go` |
| `/api/gateway/dashboard` | GET | 网关 Dashboard（成功率/延迟/费用） | 自定义 |

---

## 28. Token Manager 插件 SDK 基线修复

> **背景**：代码审计发现 ddw-token-manager 插件**自行定义了 DDWPluginBase 和 PluginState**，未继承 SDK 的 `plugin_base.py:PluginBase` 和 `plugin_state.py:PluginState`。这违反了插件 SDK 一致性原则，会导致：
> 1. 插件管理器无法通过统一接口管理状态
> 2. 事件总线无法正确路由到该插件
> 3. 测试框架无法使用标准 fixture

### 28.1 问题诊断

| 文件 | 当前实现 | SDK 标准 | 问题 |
|:-----|:---------|:---------|:-----|
| `main.py:29-35` | 自定义 `PluginState(str, Enum)` 5 个值 | `sdk/plugin_state.py:PluginState(str, Enum)` 5 个值 | 枚举值不一致（LOADING vs loading） |
| `main.py:42-87` | 自定义 `DDWPluginBase` 类 | `sdk/plugin_base.py:PluginBase` | 完全不同的接口：DDWPluginBase 无 `setup()` 钩子，无 `ConfigManager` 集成 |
| `main.py:92` | `class TokenManagerPlugin(DDWPluginBase)` | 应为 `class TokenManagerPlugin(PluginBase)` | 未继承 SDK 基类 |
| `models.py:31-33` | 自定义 `Base(DeclarativeBase)` | 应使用 SDK 的统一 Base | ORM 基类不统一 |

### 28.2 修复方案

#### 28.2.1 main.py 重写

```python
# ddw-token-manager/main.py — 修复后

"""
DDW Token Manager 插件入口

继承 SDK PluginBase，使用 SDK PluginState 状态机。

修复清单:
1. 移除自定义 DDWPluginBase → 继承 sdk.plugin_base.PluginBase
2. 移除自定义 PluginState → 使用 sdk.plugin_state.PluginState
3. 实现 PluginBase.setup() 钩子（替代 on_enable）
4. 使用 ConfigManager 管理配置
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI

# [v5.7修复] 导入 SDK 标准基类
from sdk.plugin_base import PluginBase
from sdk.plugin_state import PluginState, PluginStateInfo

logger = logging.getLogger(__name__)


class TokenManagerPlugin(PluginBase):
    """
    DDW Token Manager 插件
    
    [v5.7修复] 继承 SDK PluginBase，而非自定义 DDWPluginBase
    
    状态机（使用 SDK PluginState）:
    LOADING → ACTIVE → FAILED / DISABLED / NEEDS_UPDATE
    """
    name = "ddw-token-manager"
    version = "1.0.0"
    router_prefix = "/api/token-manager"

    def __init__(
        self,
        app: FastAPI,
        config: Optional[Dict[str, Any]] = None,
        manifest: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._state_info = PluginStateInfo(
            state=PluginState.LOADING,
            name=self.name,
            version=self.version,
        )
        super().__init__(app=app, config=config, manifest=manifest)

    def setup(self) -> None:
        """
        [v5.7修复] 实现 PluginBase.setup() 钩子
        
        替代原来的 on_enable() 方法，由 PluginBase.__init__() 自动调用。
        """
        try:
            self._setup_routes()
            self._load_ratio_config()
            self._state_info.to_active()
            logger.info("[%s] 插件已激活，版本 %s", self.name, self.version)
        except Exception as e:
            self._state_info.to_failed(code=500, message=str(e))
            logger.error("[%s] 插件激活失败: %s", self.name, e)

    def _setup_routes(self) -> None:
        """注册路由"""
        try:
            from .router import router as token_router
        except ImportError:
            from router import router as token_router
        self.router.include_router(token_router)

    def _load_ratio_config(self) -> None:
        """加载倍率配置"""
        try:
            from .config_loader import get_ratio_loader
            loader = get_ratio_loader()
            logger.info("[%s] 倍率配置已加载: %d 个模型", self.name, loader.get_model_count())
        except Exception as e:
            logger.warning("[%s] 倍率配置加载失败: %s", self.name, e)


def register(app: FastAPI) -> None:
    """插件入口函数 — 由 PluginManager 调用"""
    plugin = TokenManagerPlugin(app=app)
    plugin.register()  # PluginBase.register() 挂载路由
```

#### 28.2.2 models.py 统一 ORM 基类

```python
# ddw-token-manager/models.py — 修复后

"""
SQLAlchemy 数据模型 — Token 额度管理

[v5.7修复] 统一使用 core.database.base.Base
"""
from __future__ import annotations

# [v5.7修复] 从 core.database 导入统一 Base
try:
    from core.database.base import Base
except ImportError:
    from sqlalchemy.orm import DeclarativeBase
    class Base(DeclarativeBase):
        """降级基类（SDK 不可用时）"""
        pass

# ... 其余模型定义不变，但全部继承 Base ...
```

#### 28.2.3 迁移清单

| 步骤 | 操作 | 影响文件 | 回滚方案 |
|:----:|:-----|:---------|:---------|
| 1 | 移除自定义 `DDWPluginBase` 类 | `main.py` | 恢复原文件 |
| 2 | 移除自定义 `PluginState` 枚举 | `main.py` | 恢复原文件 |
| 3 | `TokenManagerPlugin` 改为继承 `PluginBase` | `main.py` | 恢复原文件 |
| 4 | 实现 `setup()` 替代 `on_enable()` | `main.py` | 恢复原文件 |
| 5 | ORM Base 统一 | `models.py` | 恢复原文件 |
| 6 | 添加 `register(app)` 入口函数 | `main.py` | 恢复原文件 |
| 7 | 单元测试全部通过 | `tests/` | 回退到步骤 1 |

### 28.3 集成测试矩阵

| 测试场景 | 测试方法 | 预期结果 |
|:---------|:---------|:---------|
| 插件加载 | `TokenManagerPlugin(app)` | 状态 → ACTIVE |
| 路由挂载 | `GET /api/token-manager/subscriptions` | 200 OK |
| 倍率查询 | `get_ratio_loader().get_input_ratio("gpt-4o")` | 返回正确倍率 |
| 预消费 | `pre_consume(user_id=1, model="gpt-4o")` | 返回 allowed=True |
| 后消费 | `post_consume(user_id=1, ...)` | quota 正确更新 |
| 状态机 | `plugin.state` | 返回 `PluginState.ACTIVE` |
| 插件禁用 | 模拟异常触发 `to_failed()` | 状态 → FAILED |
| 插件恢复 | 重新 `setup()` | 状态 → ACTIVE |

---

## 29. 插件开发规范硬约束

> **背景**：v5.6 §23/§26 已有插件开发指南，但都是建议性质。v5.7 将关键规范升级为**强制约束**——不满足则插件无法加载。

### 29.1 强制约束清单

| # | 约束 | 级别 | 检查方式 | 不满足后果 |
|:-:|:-----|:----:|:---------|:-----------|
| 1 | **必须继承 `sdk/plugin_base.py:PluginBase`** | P0 | `PluginManager._validate_plugin()` | 拒绝加载，抛出 `PluginIncompatibleError` |
| 2 | **必须使用 `sdk/plugin_state.py:PluginState`** | P0 | 代码静态扫描（ruff/import check） | 拒绝加载 |
| 3 | **`manifest.yaml` 必须包含 `permissions` 字段** | P0 | manifest 解析验证 | 拒绝安装 |
| 4 | **`manifest.yaml` 必须包含 `config_schema` 字段** | P1 | manifest 解析验证 | 警告但允许加载 |
| 5 | **每个插件必须有独立 Git 仓库** | P1 | manifest 中声明 `repository` URL | Marketplace 不接受上架 |
| 6 | **测试覆盖率 ≥ 80%** | P1 | CI `pytest --cov` 门禁 | CI 红灯，不允许合并 |
| 7 | **`__init__.py` 必须暴露 `register(app)` 函数** | P0 | `PluginManager._load_plugin()` | 拒绝加载 |
| 8 | **manifest.yaml 的 `dependencies` 必须是字典** | P0 | manifest 解析 | 报 `AttributeError`（已知 pitfall） |

### 29.2 PluginManager 验证增强

```python
# core/plugin_manager/validator.py — [v5.7新增]

import importlib
import inspect
from typing import Any

from sdk.plugin_base import PluginBase


class PluginValidator:
    """
    插件加载前验证器
    
    验证规则:
    1. __init__.py 必须有 register(app) 函数
    2. register() 返回的实例必须是 PluginBase 的子类
    3. manifest.yaml 必须包含 permissions 字段
    4. 状态机必须使用 SDK PluginState
    """
    
    def validate_manifest(self, manifest: dict) -> list[str]:
        """验证 manifest.yaml，返回错误列表"""
        errors = []
        
        # 必须字段
        required_fields = ["name", "version", "engine", "permissions"]
        for field in required_fields:
            if field not in manifest:
                errors.append(f"manifest.yaml 缺少必填字段: {field}")
        
        # dependencies 必须是字典（已知 pitfall）
        deps = manifest.get("dependencies", {})
        if not isinstance(deps, dict):
            errors.append(
                f"manifest.yaml 的 dependencies 必须是字典，"
                f"当前类型: {type(deps).__name__}"
            )
        
        return errors
    
    def validate_plugin_class(self, plugin_class: type) -> list[str]:
        """验证插件类是否符合 SDK 规范"""
        errors = []
        
        # 必须继承 PluginBase
        if not issubclass(plugin_class, PluginBase):
            errors.append(
                f"插件类 {plugin_class.__name__} 必须继承 "
                f"sdk.plugin_base.PluginBase"
            )
        
        # 必须实现 setup() 方法
        if not hasattr(plugin_class, 'setup') or \
           plugin_class.setup is PluginBase.setup:
            errors.append(
                f"插件类 {plugin_class.__name__} 必须实现 setup() 方法"
            )
        
        return errors
    
    def validate_register_function(self, module) -> list[str]:
        """验证模块中的 register 函数"""
        errors = []
        
        if not hasattr(module, 'register'):
            errors.append("插件模块缺少 register(app) 函数")
            return errors
        
        if not callable(module.register):
            errors.append("register 不是可调用对象")
        
        return errors
```

### 29.3 插件目录结构标准（强制）

```
plugins/<plugin-name>/
├── manifest.yaml              # [必须] 含 permissions + config_schema
├── __init__.py                # [必须] 含 register(app) 函数
├── sdk/                       # [可选] 软链接到 SDK
│   └── plugin_base.py → ../../sdk/plugin_base.py
├── models/                    # [可选] SQLAlchemy 模型
├── routes/                    # [可选] API 路由
├── services/                  # [可选] 业务逻辑
├── tests/                     # [必须] 测试目录
│   ├── __init__.py
│   ├── conftest.py            # 使用 SDK 标准 fixture
│   └── test_*.py              # 测试文件
├── README.md                  # [推荐] 插件说明
└── requirements.txt           # [可选] 特有依赖
```

### 29.4 测试覆盖率门禁

```yaml
# .github/workflows/plugin-ci.yml — [v5.7新增]

name: Plugin CI
on: [push, pull_request]

jobs:
  test-plugin:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        plugin:
          - ddw-token-manager
          - ddw-llm-gateway
          # 动态发现所有插件目录
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      
      # 静态检查
      - name: Lint
        run: ruff check plugins/${{ matrix.plugin }}/
      
      # 编译检查
      - name: Compile Check
        run: python -m py_compile plugins/${{ matrix.plugin }}/__init__.py
      
      # 测试 + 覆盖率
      - name: Test
        run: |
          pytest plugins/${{ matrix.plugin }}/tests/ \
            --cov=plugins/${{ matrix.plugin }} \
            --cov-fail-under=80 \
            -v
      
      # Manifest 验证
      - name: Validate Manifest
        run: |
          python -c "
          import yaml, sys
          with open('plugins/${{ matrix.plugin }}/manifest.yaml') as f:
              m = yaml.safe_load(f)
          required = ['name', 'version', 'engine', 'permissions']
          for r in required:
              if r not in m:
                  print(f'FAIL: missing {r}')
                  sys.exit(1)
          if not isinstance(m.get('dependencies', {}), dict):
              print('FAIL: dependencies must be dict')
              sys.exit(1)
          print('PASS: manifest validation')
          "
```

---

## 30. One API 设计模式 Python 迁移清单

> **背景**：One API 22,179 行 Go 代码中提炼出 6 大核心设计模式，需要完整迁移到 DDW Python 生态。本节逐项列出迁移方案。

### 30.1 适配器模式 → Python ABC

| One API 实现 | DDW 迁移方案 | 状态 |
|:-------------|:-------------|:----:|
| `relay/adaptor.go:Adaptor` 接口 (19 个方法) | `ddw_llm_gateway/adaptor.py:BaseAdaptor(ABC)` | 📋 待开发 |
| `relay/adaptor/adaptor_openai/` (OpenAI 适配器) | `ddw_llm_gateway/adaptors/openai.py:OpenAIAdaptor(BaseAdaptor)` | 📋 待开发 |
| `relay/adaptor/adaptor_claude/` (Claude 适配器) | `ddw_llm_gateway/adaptors/claude.py:ClaudeAdaptor(BaseAdaptor)` | 📋 待开发 |
| `relay.GetAdaptor()` 工厂函数 | `AdaptorRegistry.create(channel_type) -> BaseAdaptor` | 📋 待开发 |

```python
# ddw_llm_gateway/adaptor.py — 适配器抽象基类

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

class BaseAdaptor(ABC):
    """
    LLM 适配器抽象基类
    
    映射: One API relay/adaptor.go:Adaptor 接口
    19 个 Adaptor 实现 → Python ABC 继承
    
    核心方法:
    1. init()         — 初始化（设置 API Key、Base URL）
    2. do_request()   — 发送请求到上游
    3. do_response()  — 处理响应（转换为标准格式）
    """
    
    @abstractmethod
    async def init(self, channel_config: dict) -> None:
        """初始化适配器"""
        ...
    
    @abstractmethod
    async def do_request(self, request: dict) -> dict:
        """发送请求到上游 LLM"""
        ...
    
    @abstractmethod
    async def do_stream_request(self, request: dict) -> AsyncGenerator[str, None]:
        """发送流式请求"""
        ...
    
    @abstractmethod
    def convert_request(self, standard_request: dict) -> dict:
        """标准格式 → Provider 格式"""
        ...
    
    @abstractmethod
    def convert_response(self, provider_response: dict) -> dict:
        """Provider 格式 → 标准格式"""
        ...


class AdaptorRegistry:
    """
    适配器注册表
    
    映射: One API relay/adaptor.go 中的 switch-case
    """
    _registry: dict[int, type[BaseAdaptor]] = {}
    
    @classmethod
    def register(cls, channel_type: int, adaptor_class: type[BaseAdaptor]):
        cls._registry[channel_type] = adaptor_class
    
    @classmethod
    def create(cls, channel_type: int) -> BaseAdaptor:
        adaptor_class = cls._registry.get(channel_type)
        if not adaptor_class:
            raise ValueError(f"未注册的渠道类型: {channel_type}")
        return adaptor_class()
```

### 30.2 双层缓存 → Redis + aiocache

| One API 实现 | DDW 迁移方案 | 状态 |
|:-------------|:-------------|:----:|
| `model/cache.go:channelSyncLock` (RWMutex) | `aiocache` 内存缓存 + `redis-py` 分布式缓存 | 📋 待开发 |
| `CacheGetUserGroup()` 用户组缓存 | `aiocache.cached(ttl=300)` 装饰器 | 📋 待开发 |
| `CacheGetRandomSatisfiedChannel()` 渠道缓存 | 双层: L1 内存(aiocache) + L2 Redis | 📋 待开发 |
| 定时同步 `SyncChannelCache()` | `aiocache` TTL 自动失效 + Redis Pub/Sub 通知 | 📋 待开发 |

```python
# core/cache/dual_layer.py — [v5.7新增]

from __future__ import annotations
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

class DualLayerCache:
    """
    双层缓存架构
    
    映射: One API model/cache.go 的双层设计
    L1: 内存缓存（进程内，aiocache）
    L2: Redis 缓存（分布式，redis-py）
    
    策略:
    - 读: L1 → L2 → 回源
    - 写: 写 L2 + 通知 L1 失效
    - 失效: TTL 自动 + Pub/Sub 主动通知
    """
    
    def __init__(self, redis_client=None, l1_ttl: int = 60):
        self._redis = redis_client
        self._l1: dict[str, Any] = {}
        self._l1_ttl = l1_ttl
    
    async def get(self, key: str) -> Optional[Any]:
        """L1 → L2 → None"""
        # L1
        if key in self._l1:
            return self._l1[key]
        # L2
        if self._redis:
            value = await self._redis.get(key)
            if value:
                self._l1[key] = value  # 回填 L1
                return value
        return None
    
    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """写 L2 + L1"""
        if self._redis:
            await self._redis.setex(key, ttl, value)
        self._l1[key] = value
    
    async def invalidate(self, key: str) -> None:
        """主动失效"""
        self._l1.pop(key, None)
        if self._redis:
            await self._redis.delete(key)
```

### 30.3 批量更新 → asyncio.Queue

| One API 实现 | DDW 迁移方案 | 状态 |
|:-------------|:-------------|:----:|
| `model/utils.go:BatchUpdateStores` (内存队列) | `asyncio.Queue` + 定时刷写 | 📋 待开发 |
| 按类型分锁 `batchUpdateLocks[]` | `asyncio.Lock` per channel_id | 📋 待开发 |
| `InitBatchUpdater()` 后台 goroutine | `asyncio.create_task()` 定时消费 | 📋 待开发 |

```python
# core/cache/batch_updater.py — [v5.7新增]

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

@dataclass
class BatchUpdateItem:
    """批量更新条目"""
    entity_type: str    # "channel" | "token" | "user"
    entity_id: int
    field: str
    value: Any

class BatchUpdater:
    """
    批量更新器
    
    映射: One API model/utils.go:BatchUpdateStores
    
    原理:
    1. 高频写操作先放入 asyncio.Queue（内存聚合）
    2. 每 N 秒或队列满 M 条时批量刷写到数据库
    3. 减少数据库写入压力（One API 的核心性能优化）
    """
    
    def __init__(self, db_session_factory=None, flush_interval: float = 5.0):
        self._queue: asyncio.Queue[BatchUpdateItem] = asyncio.Queue(maxsize=10000)
        self._flush_interval = flush_interval
        self._running = False
        self._task = None
    
    async def add(self, item: BatchUpdateItem) -> None:
        """添加更新条目"""
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            logger.warning("批量更新队列已满，直接写入数据库")
            await self._flush_single(item)
    
    async def start(self) -> None:
        """启动后台消费"""
        self._running = True
        self._task = asyncio.create_task(self._consume_loop())
    
    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
    
    async def _consume_loop(self) -> None:
        """定时批量刷写"""
        while self._running:
            await asyncio.sleep(self._flush_interval)
            await self._flush_all()
    
    async def _flush_all(self) -> None:
        """批量刷写所有待更新项"""
        items = []
        while not self._queue.empty() and len(items) < 1000:
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        
        if items:
            # 按 entity_type 分组批量更新
            logger.debug("批量刷写 %d 条更新", len(items))
            # 实际实现：SQLAlchemy bulk_update_mappings()
    
    async def _flush_single(self, item: BatchUpdateItem) -> None:
        """单条直接写入"""
        pass
```

### 30.4 预消费/后消费 → 异步协程

| One API 实现 | DDW 迁移方案 | 状态 |
|:-------------|:-------------|:----:|
| `relay/controller/helper.go:preConsumeQuota()` | `async def pre_consume()` + asyncio.Lock | ✅ §27.7 已设计 |
| `relay/controller/helper.go:postConsumeQuota()` | `async def post_consume()` + 差额结算 | ✅ §27.7 已设计 |
| 差额补偿 `quota = actual - pre_consumed` | 同上 | ✅ |

### 30.5 配置热更新 → Pydantic Settings

| One API 实现 | DDW 迁移方案 | 状态 |
|:-------------|:-------------|:----:|
| `common/config/config.go:OptionMapRWMutex` | `pydantic_settings.BaseSettings` + 文件监听 | 📋 待开发 |
| `model.SyncOptions()` 定时同步 | `watchfiles` 文件变更监听 | 📋 待开发 |
| `model.InitOptionMap()` 首次加载 | Pydantic Settings 构造函数 | 📋 待开发 |

```python
# core/config/hot_reload.py — [v5.7新增]

from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from typing import Any, Callable

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

class HotReloadConfig:
    """
    配置热更新
    
    映射: One API common/config.go + model.SyncOptions()
    
    原理:
    1. 首次从 YAML 加载到 Pydantic Settings 对象
    2. watchfiles 监听文件变更
    3. 变更时自动重新加载 + 通知订阅者
    """
    
    def __init__(self, config_path: str | Path):
        self._config_path = Path(config_path)
        self._settings: dict[str, Any] = {}
        self._subscribers: list[Callable] = []
        self._last_mtime: float = 0
    
    def load(self) -> dict[str, Any]:
        """首次加载配置"""
        import yaml
        if self._config_path.exists():
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._settings = yaml.safe_load(f) or {}
            self._last_mtime = self._config_path.stat().st_mtime
        return self._settings
    
    def subscribe(self, callback: Callable) -> None:
        """订阅配置变更"""
        self._subscribers.append(callback)
    
    async def watch(self) -> None:
        """后台监听文件变更"""
        try:
            from watchfiles import awatch
            async for changes in awatch(self._config_path.parent):
                for change_type, path in changes:
                    if str(path) == str(self._config_path):
                        self._reload()
        except ImportError:
            logger.warning("watchfiles 未安装，配置热更新降级为轮询")
            await self._poll_watch()
    
    def _reload(self) -> None:
        """重新加载配置"""
        import yaml
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                new_settings = yaml.safe_load(f) or {}
            self._settings = new_settings
            self._last_mtime = self._config_path.stat().st_mtime
            
            # 通知订阅者
            for callback in self._subscribers:
                try:
                    callback(self._settings)
                except Exception as e:
                    logger.error("配置变更回调失败: %s", e)
            
            logger.info("配置已热更新: %s", self._config_path)
        except Exception as e:
            logger.error("配置热更新失败: %s", e)
    
    async def _poll_watch(self) -> None:
        """降级：轮询检测文件变更"""
        while True:
            await asyncio.sleep(5)
            mtime = self._config_path.stat().st_mtime
            if mtime > self._last_mtime:
                self._reload()
```

### 30.6 适配器模式完整映射表

| # | One API Adaptor | DDW Adaptor | 请求格式 | 响应格式 | 流式支持 |
|:-:|:----------------|:-------------|:---------|:---------|:--------:|
| 1 | `adaptor_openai` | `OpenAIAdaptor` | OpenAI 原生 | OpenAI 原生 | ✅ |
| 2 | `adaptor_claude` | `ClaudeAdaptor` | Anthropic 原生 | → OpenAI 格式 | ✅ |
| 3 | `adaptor_gemini` | `GeminiAdaptor` | Google 原生 | → OpenAI 格式 | ✅ |
| 4 | `adaptor_azure` | `AzureOpenAIAdaptor` | Azure 格式 | Azure 格式 | ✅ |
| 5 | `adaptor_baidu` | `BaiduAdaptor` | 百度原生 | → OpenAI 格式 | ✅ |
| 6 | `adaptor_zhipu` | `ZhipuAdaptor` | 智谱原生 | → OpenAI 格式 | ✅ |
| 7 | `adaptor_deepseek` | `DeepSeekAdaptor` | DeepSeek 原生 | DeepSeek 原生 | ✅ |
| 8 | `adaptor_minimax` | `MiniMaxAdaptor` | MiniMax 原生 | → OpenAI 格式 | ✅ |
| 9 | `adaptor_ollama` | `OllamaAdaptor` | Ollama 原生 | → OpenAI 格式 | ✅ |
| 10-19 | 其他 10 种 | 后续扩展 | — | — | — |

---

## 31. 安全补强清单

> **背景**：One API 源码安全审计发现 6 项安全问题（`one-api-architecture-analysis-deepseek.md` §4），需要在 DDW 中逐一修复。

### 31.1 安全漏洞清单

| # | 漏洞 | One API 现状 | DDW 修复方案 | 优先级 | 映射文档 |
|:-:|:-----|:-------------|:-------------|:------:|:---------|
| S1 | **默认密码 123456** | `model/main.go:28` 硬编码 root 密码 | 首次启动强制修改密码 + 强度校验 | P0 | DeepSeek §4.1 |
| S2 | **API Key JSON 序列化泄露** | Channel 的 `key` 字段 JSON 直出 | `json:"-"` 隐藏 / Pydantic `field_serializer` | P0 | DeepSeek §4.2 |
| S3 | **CORS 全开 `*`** | `router/api.go:CORS` 允许所有来源 | 白名单域名 + 环境变量配置 | P0 | DeepSeek §4.3 |
| S4 | **Session Cookie 不安全** | Gin Session Cookie 无安全标记 | JWT Token + HttpOnly + Secure + SameSite | P0 | DeepSeek §4.4 |
| S5 | **无 CSRF 防护** | Cookie 认证无 CSRF Token | SameSite=Strict + CSRF Token 验证 | P1 | DeepSeek §4.5 |
| S6 | **eval() 安全风险** | `model/ratio.go` 使用 eval 解析倍率表达式 | 限制 eval 环境 + 安全沙箱求值 | P1 | DeepSeek §4.6 |

### 31.2 S1 修复：强制首次修改密码

```python
# core/auth/first_login.py — [v5.7新增]

from __future__ import annotations
import re
import logging
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

class FirstLoginGuard:
    """
    首次登录强制修改密码
    
    One API 问题: root 密码硬编码为 123456
    
    修复:
    1. 首次启动创建 admin 时生成随机密码
    2. 要求首次登录时强制修改密码
    3. 密码强度校验（≥8位，含大小写+数字+特殊字符）
    """
    
    MIN_PASSWORD_LENGTH = 8
    PASSWORD_PATTERN = re.compile(
        r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&#])[A-Za-z\d@$!%*?&#]{8,}$"
    )
    
    @staticmethod
    def validate_password(password: str) -> tuple[bool, str]:
        """密码强度校验"""
        if len(password) < FirstLoginGuard.MIN_PASSWORD_LENGTH:
            return False, f"密码长度不足 {FirstLoginGuard.MIN_PASSWORD_LENGTH} 位"
        
        if not FirstLoginGuard.PASSWORD_PATTERN.match(password):
            return False, (
                "密码必须包含: 大写字母、小写字母、数字、特殊字符(@$!%*?&#)"
            )
        
        return True, ""
    
    @staticmethod
    def generate_temp_password() -> str:
        """生成临时密码（首次启动）"""
        import secrets
        import string
        chars = string.ascii_letters + string.digits + "@$!%*?&#"
        while True:
            password = ''.join(secrets.choice(chars) for _ in range(12))
            ok, _ = FirstLoginGuard.validate_password(password)
            if ok:
                return password
```

### 31.3 S2 修复：API Key 序列化隐藏

```python
# core/security/serialization.py — [v5.7新增]

from pydantic import BaseModel, field_serializer

class SafeChannelResponse(BaseModel):
    """安全的渠道响应模型 — 隐藏 API Key"""
    id: int
    name: str
    type: int
    status: int
    base_url: str
    models: str
    
    @field_serializer("key")
    def mask_key(self, value: str) -> str:
        """API Key 脱敏: sk-abc...xyz → sk-a***xyz"""
        if not value or len(value) < 8:
            return "***"
        return f"{value[:4]}***{value[-3:]}"
```

### 31.4 S3 修复：CORS 白名单

```python
# core/middleware/cors.py — [v5.7新增]

from fastapi.middleware.cors import CORSMiddleware

def setup_cors(app, allowed_origins: list[str] = None):
    """
    CORS 配置 — 白名单模式
    
    One API 问题: CORS("*") 允许所有来源
    
    修复: 从环境变量读取白名单
    """
    import os
    
    if allowed_origins is None:
        raw = os.getenv("DDW_CORS_ORIGINS", "http://localhost:8500")
        allowed_origins = [o.strip() for o in raw.split(",")]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,      # 白名单，非 "*"
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
        max_age=600,
    )
```

### 31.5 S4 修复：JWT 安全加固

```python
# core/auth/jwt_security.py — [v5.7新增]

from datetime import datetime, timedelta
from typing import Optional
import jwt
import secrets

class SecureTokenManager:
    """
    JWT Token 安全管理
    
    One API 问题: Session Cookie 无安全标记
    
    修复:
    1. 使用 JWT 替代 Session Cookie
    2. 短过期时间（15分钟） + Refresh Token（7天）
    3. Token 黑名单（Redis）
    """
    
    def __init__(self, secret_key: str = None):
        self._secret = secret_key or secrets.token_hex(32)
    
    def create_access_token(
        self,
        user_id: int,
        role: int,
        expires_delta: timedelta = timedelta(minutes=15),
    ) -> str:
        """创建短期 Access Token"""
        payload = {
            "sub": user_id,
            "role": role,
            "exp": datetime.utcnow() + expires_delta,
            "iat": datetime.utcnow(),
            "jti": secrets.token_hex(16),  # 唯一 ID，用于黑名单
        }
        return jwt.encode(payload, self._secret, algorithm="HS256")
    
    def create_refresh_token(self, user_id: int) -> str:
        """创建长期 Refresh Token"""
        payload = {
            "sub": user_id,
            "type": "refresh",
            "exp": datetime.utcnow() + timedelta(days=7),
            "jti": secrets.token_hex(16),
        }
        return jwt.encode(payload, self._secret, algorithm="HS256")
```

---

## 32. 性能补强清单

> **背景**：One API 源码分析发现 3 项性能关键路径优化（`one-api-architecture-analysis-deepseek.md` §6），DDW 需要对标实现。

### 32.1 性能优化清单

| # | 优化项 | One API 实现 | DDW 方案 | 预期收益 | 状态 |
|:-:|:------|:-------------|:---------|:---------|:----:|
| P1 | **直传模式** | OpenAI 原生请求跳过请求/响应转换 | `DirectPassAdaptor` | 延迟降低 30-50% | 📋 待开发 |
| P2 | **连接池配置** | `client.Init()` 配置 MaxIdle/MaxOpen/MaxLifetime | `httpx.AsyncClient` 连接池 | 并发能力提升 3x | 📋 待开发 |
| P3 | **Token 近似计算** | `openai.InitTokenEncoders()` tiktoken | `len(text) * 0.38` 快速估算 | 初始化时间 -2s | 📋 待开发 |

### 32.2 P1 直传模式

```python
# ddw_llm_gateway/direct_pass.py — [v5.7新增]

from __future__ import annotations
import logging
from typing import AsyncGenerator
import httpx

logger = logging.getLogger(__name__)

class DirectPassAdaptor:
    """
    直传模式 — OpenAI 原生请求跳过转换
    
    One API 优化: 如果客户端发送的就是 OpenAI 格式请求
    且目标渠道也是 OpenAI 兼容的，则跳过:
    1. 请求解析和验证（省 ~2ms）
    2. 请求格式转换（省 ~5ms）
    3. 响应格式转换（省 ~5ms）
    
    总延迟降低: 10-15ms (非流式) / 30-50% (流式首 token)
    """
    
    def __init__(self, http_client: httpx.AsyncClient):
        self._client = http_client
    
    async def direct_relay(
        self,
        upstream_url: str,
        api_key: str,
        request_body: bytes,
        headers: dict,
    ) -> httpx.Response:
        """直接转发，不做格式转换"""
        relay_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": headers.get("Accept", "application/json"),
        }
        
        return await self._client.post(
            upstream_url,
            content=request_body,
            headers=relay_headers,
            timeout=60.0,
        )
    
    async def direct_stream_relay(
        self,
        upstream_url: str,
        api_key: str,
        request_body: bytes,
    ) -> AsyncGenerator[bytes, None]:
        """流式直传"""
        relay_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        async with self._client.stream(
            "POST",
            upstream_url,
            content=request_body,
            headers=relay_headers,
            timeout=60.0,
        ) as response:
            async for chunk in response.aiter_bytes():
                yield chunk
```

### 32.3 P2 连接池配置

```python
# core/http/client_pool.py — [v5.7新增]

import httpx
from typing import Optional

class HTTPClientPool:
    """
    HTTP 连接池管理
    
    One API 优化: client.Init() 中配置 MaxIdle/MaxOpen/MaxLifetime
    
    Python httpx 对应参数:
    - max_connections = MaxOpen（最大连接数）
    - max_keepalive_connections = MaxIdle（空闲连接数）
    - keepalive_expiry = MaxLifetime（空闲连接最大存活时间）
    """
    
    _instance: Optional[httpx.AsyncClient] = None
    
    @classmethod
    def get_client(
        cls,
        max_connections: int = 100,
        max_keepalive: int = 20,
        keepalive_expiry: int = 30,
        timeout: float = 60.0,
    ) -> httpx.AsyncClient:
        """获取全局 HTTP 客户端（单例）"""
        if cls._instance is None or cls._instance.is_closed:
            cls._instance = httpx.AsyncClient(
                limits=httpx.Limits(
                    max_connections=max_connections,
                    max_keepalive_connections=max_keepalive,
                    keepalive_expiry=keepalive_expiry,
                ),
                timeout=httpx.Timeout(timeout),
                follow_redirects=True,
            )
        return cls._instance
    
    @classmethod
    async def close(cls) -> None:
        """关闭连接池"""
        if cls._instance and not cls._instance.is_closed:
            await cls._instance.aclose()
```

### 32.4 P3 Token 近似计算

```python
# core/llm/token_estimator.py — [v5.7新增]

class TokenEstimator:
    """
    Token 近似计算器
    
    One API: 使用 tiktoken 编码器精确计算（初始化慢，~2s）
    DDW: 提供两种模式
    1. 快速模式: len(text) * 0.38（中文文本，初始化 0ms）
    2. 精确模式: tiktoken 编码（初始化 ~2s，但精确）
    
    用途:
    - 预消费阶段: 快速模式（够用）
    - 后消费阶段: 精确模式（如果可用）
    """
    
    # 中文 + 英文混合文本的经验系数
    CHINESE_RATIO = 0.38
    ENGLISH_RATIO = 0.25
    
    @classmethod
    def estimate_fast(cls, text: str) -> int:
        """快速估算（0ms 初始化）"""
        # 中文字符占比越高，系数越大
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        ratio = cls.CHINESE_RATIO if chinese_chars / max(len(text), 1) > 0.3 else cls.ENGLISH_RATIO
        return max(1, int(len(text) * ratio))
    
    @classmethod
    def estimate_precise(cls, text: str) -> int:
        """精确计算（需要 tiktoken）"""
        try:
            import tiktoken
            enc = tiktoken.encoding_for_model("gpt-4")
            return len(enc.encode(text))
        except ImportError:
            return cls.estimate_fast(text)
```

---

## 33. 开发里程碑与排期

### Phase 1: ddw-llm-gateway 插件开发（Week 1-4）

| 周 | 任务 | 交付物 | 依赖 |
|:--:|:-----|:-------|:-----|
| W1 | 渠道管理（Channel Manager） | Channel 模型 + CRUD API + YAML 配置加载 | — |
| W1 | 适配器框架 | BaseAdaptor ABC + OpenAIAdaptor + AdaptorRegistry | — |
| W2 | 负载均衡引擎 | LoadBalancer + 优先级+权重随机选择 | W1 |
| W2 | 失败重试+自动禁用 | CircuitBreaker + ChannelHealthMonitor | W1 |
| W3 | 流式 SSE 转发 | StreamRelay + 直传模式 | W1 |
| W3 | Token Manager 集成 | QuotaIntegration（预消费/后消费） | ddw-token-manager |
| W4 | 集成测试 | 端到端测试覆盖 ≥ 80% | W1-3 |
| W4 | API 文档 | FastAPI OpenAPI 文档 | W1-3 |

### Phase 2: ddw-token-manager SDK 基线修复 + 集成（Week 5-6）

| 周 | 任务 | 交付物 | 依赖 |
|:--:|:-----|:-------|:-----|
| W5 | SDK 基线修复 | 移除自定义 DDWPluginBase/PluginState → 继承 SDK | — |
| W5 | ORM Base 统一 | models.py 统一使用 core.database.base.Base | — |
| W5 | 集成测试 | Token Manager + LLM Gateway 联调测试 | Phase 1 |
| W6 | 数据库迁移脚本 | Alembic migration for token_* 表 | W5 |
| W6 | 迁移验证 | 旧数据迁移 + 新表创建 + 数据完整性 | W5 |

### Phase 3: 插件市场 MVP（Week 7-10）

| 周 | 任务 | 交付物 | 依赖 |
|:--:|:-----|:-------|:-----|
| W7 | 插件市场协议 | Marketplace Registry + 搜索/分类 API | — |
| W7 | 插件打包格式 | .ddwplugin 打包/解包工具 | — |
| W8 | 插件上架流程 | 上传 → 验证 → AI Eval 门禁 → 上架 | Phase 1+2 |
| W9 | 插件安装/卸载 | PluginManager 完整生命周期管理 | — |
| W10 | 插件市场前端 | Vue 3 CDN 搜索/安装/评分页面 | W7-9 |

### Phase 4: 安全加固 + 性能优化（Week 11-14）

| 周 | 任务 | 交付物 | 依赖 |
|:--:|:-----|:-------|:-----|
| W11 | P0 安全修复 | 强制改密码 + API Key 隐藏 + CORS 白名单 | — |
| W12 | P0 安全修复 | JWT 加固 + CSRF 防护 | — |
| W13 | 性能优化 | 连接池 + Token 近似计算 + 直传模式 | — |
| W14 | 安全审计 | 渗透测试 + 代码审计 + 合规检查 | W11-13 |

### Phase 5: GitHub 开源准备（Week 15-16）

| 周 | 任务 | 交付物 | 依赖 |
|:--:|:-----|:-------|:-----|
| W15 | README 重写 | 完整 README + 快速开始 + 架构图 | All |
| W15 | CI/CD 完善 | GitHub Actions + 插件 CI + 覆盖率门禁 | — |
| W16 | 开源清理 | 移除私有代码 + Apache 2.0 + CONTRIBUTING.md | — |
| W16 | 发布 | GitHub Release v1.0.0-rc1 | — |

### 总排期汇总

```
Week 1-4:   ████████████ Phase 1: LLM Gateway 插件
Week 5-6:   ██████ Phase 2: Token Manager 修复 + 集成
Week 7-10:  ████████████ Phase 3: 插件市场 MVP
Week 11-14: ████████████ Phase 4: 安全 + 性能
Week 15-16: ██████ Phase 5: GitHub 开源

总计: 16 周（4 个月）
```

---

## 34. 变更记录

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v5.6 | 2026-07-12 | 基于 DeepSeek + MiMo 双 LLM 分析合并 |
| **v5.7** | **2026-07-13** | **工程补强路线图：LLM Gateway 插件 + SDK 基线修复 + 安全/性能补强 + One API 迁移** |

**v5.7 变更统计**：

| 类型 | 数量 |
|:-----|:----:|
| 新增章节 | 8（§27-§34） |
| 新增代码示例 | 12 个核心模块 |
| 迁移映射表 | 6 项 One API 设计模式 |
| 安全补丁 | 6 项（P0×4 + P1×2） |
| 性能优化 | 3 项 |
| 开发排期 | 16 周 5 阶段 |

---

## 35. 质量评估（DeepSeek V4 Pro 视角）

> 以 PRD v5.6 为基准，从 DeepSeek V4 Pro 的技术架构评估视角对 PRD v5.7 进行质量评估。

### 35.1 评估方法论

采用 DeepSeek V4 Pro 的 5 维度评估框架（与 v5.6 评估保持一致）：

| 维度 | 权重 | 评估要点 |
|:-----|:----:|:---------|
| 架构完整性 | 25% | 模块划分清晰度、接口定义完整度、依赖关系合理性 |
| 一键部署 | 20% | 部署脚本完整度、环境依赖最小化、文档可操作性 |
| 插件开发 | 20% | SDK 规范完整度、插件模板可用性、测试框架 |
| GitHub 生态 | 20% | README 质量、CI/CD 完整度、开源合规性 |
| 技术栈 | 15% | 技术选型合理性、性能预期、可维护性 |

### 35.2 v5.7 vs v5.6 对比评估

| 维度 | v5.6 评分 | v5.7 评分 | 变化 | 改进来源 |
|:-----|:---------:|:---------:|:----:|:---------|
| **架构完整性** | 7.5 | **8.5** | +1.0 | §27 LLM Gateway 完整规格（51 种渠道+负载均衡+断路器+流式转发）；§30 One API 6 大设计模式完整迁移清单 |
| **一键部署** | 7.5 | **8.0** | +0.5 | §33 完整 16 周排期（从 WBS 概要到可执行排期）；§27.2 插件 manifest 完整定义 |
| **插件开发** | 8.0 | **9.0** | +1.0 | §28 SDK 基线修复（消除自定义基类）；§29 8 项强制约束（从建议→强制）；§29.4 CI 覆盖率门禁 |
| **GitHub 生态** | 7.0 | **7.5** | +0.5 | §33 Phase 5 完整开源准备流程；§29.3 标准插件目录结构 |
| **技术栈** | 7.0 | **8.0** | +1.0 | §32 3 项性能优化（直传/连接池/Token 近似）；§31 6 项安全补丁；§30.2 双层缓存方案 |
| **总分** | **7.4** | **8.3** | **+0.9** | — |

### 35.3 详细维度分析

#### 35.3.1 架构完整性（8.5/10）

**优点**：
- LLM Gateway 插件规格（§27）非常完整，从 One API 的 51 种渠道类型到负载均衡、断路器、流式转发形成了完整闭环
- 适配器模式迁移（§30.1）定义了清晰的 ABC 基类和注册表，避免了 One API 的 switch-case 反模式
- Token Manager 集成（§27.7）的预消费/后消费设计与 One API `preConsumeQuota/postConsumeQuota` 保持一致

**扣分项**：
- 渠道类型枚举只列出了约 25 种核心类型，剩余 26 种标记为"后续扩展"，完整度 ~50%
- 缺少渠道配置的版本管理方案（One API 的渠道配置热更新是关键特性）

**建议**：补齐 51 种渠道类型枚举，或至少在附录中提供完整列表。

#### 35.3.2 一键部署（8.0/10）

**优点**：
- 16 周 5 阶段排期（§33）清晰可执行，每个 Phase 有明确的依赖关系和交付物
- Phase 5 GitHub 开源准备包含了 README 重写、CI/CD、开源清理等关键步骤

**扣分项**：
- 排期基于"一人开发"假设，未考虑多人并行的依赖冲突
- install.sh 在 v5.6 §20.1 已定义但 v5.7 未增强，仍为骨架状态

**建议**：在 Phase 1 中加入 install.sh 端到端验证（ECS 环境）。

#### 35.3.3 插件开发（9.0/10）⭐ 最高分

**优点**：
- §28 的 SDK 基线修复是 v5.7 最有价值的贡献——直接消除了代码审计中发现的根本性架构违规
- §29 的 8 项强制约束设计合理，特别是 `dependencies` 必须是字典（基于已知 pitfall）
- §29.4 的 CI 覆盖率门禁（80% 门禁线）在工程实践中是合理的

**扣分项**：
- 缺少插件版本兼容性矩阵（manifest 中的 `engine` 字段与实际 SDK 版本的对应关系）
- 80% 覆盖率门禁对于新项目可能过于严格——建议 Phase 1 为 60%，Phase 3 后提升到 80%

**建议**：增加 SDK 版本兼容性声明和分阶段覆盖率提升策略。

#### 35.3.4 GitHub 生态（7.5/10）

**优点**：
- 完整的开源准备流程（Phase 5）覆盖了 README、CI、协议、CONTRIBUTING
- §29.3 标准插件目录结构有助于第三方开发者快速上手

**扣分项**：
- 仍缺少完整的 README 模板（v5.6 §25.1.1 已有骨架但未在 v5.7 中增强）
- 缺少 Issue 模板和 PR 模板（`.github/ISSUE_TEMPLATE/` 和 `.github/PULL_REQUEST_TEMPLATE.md`）
- 缺少 CHANGELOG 规范（Keep a Changelog 格式）

**建议**：在 Phase 5 中补充 GitHub 模板文件和 CHANGELOG 规范。

#### 35.3.5 技术栈（8.0/10）

**优点**：
- §32 的 3 项性能优化针对性强：直传模式（延迟降低 30-50%）、连接池（并发提升 3x）、Token 近似计算（初始化 -2s）
- §31 的 6 项安全补丁覆盖了 One API 审计报告中的所有关键漏洞
- §30.2 双层缓存方案（aiocache + Redis）兼顾了性能和分布式一致性

**扣分项**：
- `watchfiles` 依赖可能在 Windows 上有兼容性问题（§30.5）
- Token 近似计算的 0.38 系数缺乏实测验证（§32.4）
- 安全补丁缺少具体的测试用例（§31 只有修复代码，缺少 `test_first_login.py` 等）

**建议**：
1. 为 `watchfiles` 提供跨平台降级方案（轮询模式已写但需验证）
2. 用实际中文语料校准 0.38 系数
3. 为每个安全补丁编写对应的测试用例

### 35.4 与 v5.6 评分预期对比

| 维度 | v5.6 预期 | v5.7 实际 | 差异分析 |
|:-----|:---------:|:---------:|:---------|
| 架构 | 7.5 | 8.5 | 超预期——LLM Gateway 完整规格 + One API 迁移清单远超 v5.6 的粗略描述 |
| 一键部署 | 7.5 | 8.0 | 符合预期——排期更详细但未引入新部署工具 |
| 插件开发 | 8.0 | 9.0 | 超预期——SDK 基线修复消除了根本性架构违规 |
| GitHub 生态 | 7.0 | 7.5 | 略超预期——流程完整但缺少模板文件 |
| 技术栈 | 7.0 | 8.0 | 超预期——安全补丁 + 性能优化针对性强 |
| **总分** | **7.4** | **8.3** | **+0.9 超出预期** |

### 35.5 Top 3 改进建议

1. **补齐 51 种渠道类型完整枚举**（影响：架构完整性 +0.3）
   - 当前只列 ~25 种，需要补充到 51 种
   - 可参考 One API `relay/adaptor/` 目录中的所有实现

2. **为每个安全补丁编写测试用例**（影响：技术栈 +0.2 + GitHub 生态 +0.2）
   - 当前 §31 只有修复代码，缺少 `tests/test_security_*.py`
   - 特别是密码强度校验、API Key 脱敏、CORS 白名单的测试

3. **增加 SDK 版本兼容性声明**（影响：插件开发 +0.2）
   - manifest.yaml 中的 `engine: ">=0.1.0"` 需要与实际 SDK 版本号对齐
   - 建议在 SDK 中引入语义化版本（SemVer），并在 manifest 中声明兼容范围

### 35.6 总评

> **PRD v5.7 在 v5.6 的基础上实现了质的提升**——从"有规划"到"可落地"。核心亮点是 §28 的 SDK 基线修复（消除代码审计发现的根本违规）和 §27 的 LLM Gateway 完整规格（将 One API 22,179 行 Go 代码的核心能力提炼为清晰的 Python 插件设计）。
>
> **不足之处**在于部分迁移清单仍停留在"待开发"状态（§30 中 12 个模块中有 8 个标记为 📋），需要在 Phase 1-2 中逐一落地。建议在每个 Phase 结束时进行一次 v5.7 修订，将"待开发"标记更新为"已实现"或调整方案。
>
> **最终评分：8.3/10**（v5.6 基准 7.4/10，提升 +0.9）
