# PRD：ddw-trace-panel（完整 Trace 可观测性面板）v1.0.0

> 灵感来源：StaffDeck 的"完整 Trace + 可审查执行记录"（AGPL-3.0），DDW 全新 Apache 2.0 实现
> 创建日期：2026-07-31
> 依赖：PluginBase v2（需先完成 SDK-2: execution_trace）
> 许可证：Apache 2.0

---

## 零、产品概述

### 0.1 一句话定位

**ddw-trace-panel** 为 DDW 平台上所有 AI 操作提供完整、可审查、可回放的执行轨迹，让企业客户能回答"AI 为什么这么回答？"

### 0.2 核心价值

```
没有 Trace 面板时：
  用户："为什么 AI 拒绝了客户的退款申请？"
  开发者："呃...让我翻一下日志...可能是 prompt 的问题...也可能是知识库..."
  客户："你们连 AI 为什么这么决策都不知道？"

有 Trace 面板时：
  用户：点击会话 → 查看 Trace → "哦，LLM 在审批节点查到《退款政策》第3条明确禁止此类退款"
  客户："明白了，有依据。"
```

---

## 一、架构设计

### 1.1 整体架构

```
┌─────────────────────────────────────────────────┐
│                 ddw-trace-panel                   │
│                                                   │
│  ┌──────────────┐  ┌──────────────┐              │
│  │ Trace        │  │ Trace        │              │
│  │ Collector    │  │ Storage      │              │
│  │ (SDK层收集)  │  │ (SQLite/PG)  │              │
│  └──────┬───────┘  └──────┬───────┘              │
│         │                 │                       │
│         ▼                 ▼                       │
│  ┌──────────────────────────────────────┐        │
│  │         Trace Query API              │        │
│  │  (按会话/插件/时间/TraceID 查询)     │        │
│  └──────────────┬───────────────────────┘        │
│                 │                                 │
│                 ▼                                 │
│  ┌──────────────────────────────────────┐        │
│  │         Trace Dashboard (前端)       │        │
│  │  - 时间线视图                        │        │
│  │  - 节点详情面板                      │        │
│  │  - Span 瀑布图                       │        │
│  │  - Token 消耗统计                    │        │
│  │  - 回放功能                          │        │
│  └──────────────────────────────────────┘        │
└─────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────┐
│  PluginBase v2 (SDK 增强)                        │
│                                                   │
│  @trace_span(name="llm_call")                    │
│  async def call_llm(self, ...):                   │
│      with self.execution_trace.span("llm_call"): │
│          # 自动记录: 入参, 耗时, token 消耗        │
│          result = await gateway.chat(...)          │
│          # 自动记录: 返回, 结束时间                │
│          return result                            │
└─────────────────────────────────────────────────┘
```

### 1.2 Trace 数据模型（OpenTelemetry 兼容）

```python
# models.py

class TraceSpan(Base):
    __tablename__ = 'trace_spans'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    trace_id = Column(String(36), nullable=False, index=True)  # 一个完整操作 = 一个 trace_id
    parent_span_id = Column(String(36), nullable=True, index=True)  # 父 Span
    
    # Span 信息
    span_name = Column(String(256), nullable=False)  # "llm_call" / "tool_call" / "knowledge_retrieval"
    span_type = Column(String(64), nullable=False, index=True)
    """
    span_type:
    - llm_call: LLM 推理调用
    - tool_call: 插件 Tool 执行
    - knowledge_retrieval: 知识库检索
    - sop_node: SOP 节点执行
    - im_message: IM 消息处理
    - human_approval: 人工审批
    - scheduler_task: 定时任务
    """
    
    # 关联
    plugin_name = Column(String(128), nullable=True, index=True)
    conversation_id = Column(String(36), nullable=True, index=True)
    sop_instance_id = Column(String(36), nullable=True, index=True)
    
    # 状态
    status = Column(String(32), default='running')  # running | success | error | timeout
    
    # 输入/输出
    input_data = Column(JSON, nullable=True)  # 入参（脱敏后）
    output_data = Column(JSON, nullable=True)  # 出参（脱敏后）
    error_message = Column(Text, nullable=True)
    
    # Token 统计
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    model_name = Column(String(128), nullable=True)
    
    # 耗时
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    
    # 元数据
    metadata = Column(JSON, nullable=True)  # 扩展字段
    tags = Column(JSON, nullable=True)  # ["production", "customer-facing"]
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_trace_trace_id', 'trace_id'),
        Index('idx_trace_conversation', 'conversation_id'),
        Index('idx_trace_plugin_type', 'plugin_name', 'span_type'),
        Index('idx_trace_started', 'started_at'),
    )
```

---

## 二、SDK 增强：PluginBase v2 execution_trace

### 2.1 PluginBase 新增代码

```python
# sdk/plugin_base.py (增量修改)

import time
import uuid
from contextlib import contextmanager
from typing import Optional
import functools

class ExecutionTrace:
    """DDW 执行 Trace 上下文管理器"""
    
    def __init__(self, plugin_name: str, trace_collector):
        self.plugin_name = plugin_name
        self.collector = trace_collector
        self._current_trace_id: Optional[str] = None
        self._span_stack: list = []
    
    def start_trace(self, conversation_id: str = None, metadata: dict = None) -> str:
        """开始一个新的 Trace"""
        self._current_trace_id = str(uuid.uuid4())
        self._span_stack = []
        # 异步写入 trace_start 事件
        return self._current_trace_id
    
    @contextmanager
    def span(self, name: str, span_type: str = "tool_call", 
             input_data: dict = None, metadata: dict = None):
        """
        创建一个 Span 上下文。
        
        用法:
            with self.execution_trace.span("send_email", "tool_call", 
                                           input_data={"to": "..."}) as span:
                result = await send_email(...)
                span.set_output(result)
                span.set_tokens(input=500, output=200)
        """
        span_id = str(uuid.uuid4())
        parent_id = self._span_stack[-1] if self._span_stack else None
        started_at = time.time()
        
        span_obj = _SpanContext(
            trace_id=self._current_trace_id,
            span_id=span_id,
            parent_span_id=parent_id,
            name=name,
            span_type=span_type,
            plugin_name=self.plugin_name,
            input_data=input_data,
            metadata=metadata,
            started_at=started_at,
        )
        
        self._span_stack.append(span_id)
        
        try:
            self.collector.record_span_start(span_obj.to_dict())
            yield span_obj
            span_obj.status = 'success'
        except Exception as e:
            span_obj.status = 'error'
            span_obj.error_message = str(e)
            raise
        finally:
            span_obj.ended_at = time.time()
            span_obj.duration_ms = int((span_obj.ended_at - started_at) * 1000)
            self._span_stack.pop()
            self.collector.record_span_end(span_obj.to_dict())
    
    def trace_span(self, name: str, span_type: str = "tool_call"):
        """装饰器版本"""
        def decorator(func):
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                with self.span(name, span_type, input_data={"args": str(args)[:200]}) as span:
                    result = await func(*args, **kwargs)
                    span.set_output(result)
                    return result
            return wrapper
        return decorator


class _SpanContext:
    """Span 上下文对象"""
    
    def __init__(self, trace_id, span_id, parent_span_id, name, span_type,
                 plugin_name, input_data, metadata, started_at):
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.name = name
        self.span_type = span_type
        self.plugin_name = plugin_name
        self.input_data = input_data
        self.metadata = metadata or {}
        self.started_at = started_at
        
        self.status = 'running'
        self.output_data = None
        self.error_message = None
        self.input_tokens = None
        self.output_tokens = None
        self.total_tokens = None
        self.model_name = None
        self.ended_at = None
        self.duration_ms = None
    
    def set_output(self, data: dict):
        """设置输出数据（脱敏后）"""
        self.output_data = self._sanitize(data) if data else None
    
    def set_tokens(self, input: int = None, output: int = None, 
                   total: int = None, model: str = None):
        self.input_tokens = input
        self.output_tokens = output
        self.total_tokens = total or ((input or 0) + (output or 0))
        self.model_name = model
    
    def _sanitize(self, data: dict) -> dict:
        """脱敏：移除 API Key、密码等敏感字段"""
        SENSITIVE_KEYS = {'api_key', 'password', 'secret', 'token', 'authorization'}
        return {k: ('***' if k.lower() in SENSITIVE_KEYS else v) 
                for k, v in data.items()}
    
    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith('_')}
```

### 2.2 使用示例

```python
# 在任何 DDW 插件中使用

class MyPlugin(PluginBase):
    """插件示例：展示 Trace 用法"""
    
    async def handle_message(self, message: str) -> str:
        # 开始一个 Trace
        trace_id = self.execution_trace.start_trace(
            conversation_id=self.conversation_id,
            metadata={"channel": "wecom"}
        )
        
        # Span 1: 意图识别
        with self.execution_trace.span("intent_classify", "llm_call",
                                        input_data={"message": message}) as span:
            intent = await self.llm.classify(message)
            span.set_output({"intent": intent})
            span.set_tokens(input=500, output=50, model="mimo-v2.5-pro")
        
        # Span 2: 知识检索
        with self.execution_trace.span("knowledge_search", "knowledge_retrieval",
                                        input_data={"query": message}) as span:
            docs = await self.knowledge.search(message, top_k=5)
            span.set_output({"docs_count": len(docs), "top_score": docs[0].score})
            span.set_tokens(input=200, output=1000)
        
        # Span 3: 生成回复
        with self.execution_trace.span("generate_response", "llm_call") as span:
            response = await self.llm.chat(system="你是客服", user=message)
            span.set_output({"response_length": len(response)})
            span.set_tokens(input=1500, output=500, model="mimo-v2.5-pro")
        
        return response
```

---

## 三、API 端点

```python
# router.py

router = APIRouter(prefix="/api/v1/plugins/ddw-trace-panel", tags=["Trace Panel"])

@router.get("/traces", response_model=PaginatedResponse[TraceSummarySchema])
async def list_traces(
    plugin_name: Optional[str] = Query(None),
    span_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    conversation_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    search: Optional[str] = Query(None, description="搜索 span name"),
    page: int = Query(1),
    page_size: int = Query(20),
    current_user = Depends(get_current_user),
):
    """列出 Trace"""

@router.get("/traces/{trace_id}", response_model=TraceDetailSchema)
async def get_trace_detail(trace_id: str = Path(...)):
    """获取 Trace 详情（含完整 Span 树）"""

@router.get("/traces/{trace_id}/timeline", response_model=TimelineSchema)
async def get_trace_timeline(trace_id: str = Path(...)):
    """获取 Trace 时间线（用于前端瀑布图）"""

@router.get("/traces/{trace_id}/replay", response_model=ReplaySchema)
async def replay_trace(trace_id: str = Path(...)):
    """
    回放 Trace——获取所有 Span 的输入/输出数据。
    用于调试"AI 为什么这么回答？"
    """

@router.get("/stats/overview", response_model=TraceStatsSchema)
async def get_trace_stats(
    days: int = Query(7, ge=1, le=90),
    current_user = Depends(get_current_user),
):
    """获取 Trace 统计概览：总调用次数、平均耗时、失败率、Token 消耗趋势"""

@router.get("/stats/tokens", response_model=TokenStatsSchema)
async def get_token_stats(
    days: int = Query(30),
    group_by: str = Query("plugin_name", description="plugin_name | model_name | span_type"),
):
    """获取 Token 消耗统计"""

@router.get("/stats/hotspots", response_model=List[HotspotSchema])
async def get_hotspots(
    days: int = Query(7),
    top_n: int = Query(10),
):
    """
    获取性能热点——最慢的 Span Top N。
    用于发现瓶颈：哪个插件的哪个操作最慢？
    """
```

---

## 四、前端：Trace Dashboard

### 4.1 核心页面

**时间线视图（Waterfall）**：类似 Chrome DevTools Network 面板的水平瀑布图，每个 Span = 一横条，宽度 ∝ 耗时，嵌套缩进显示父子关系，颜色按 span_type。

**节点详情面板**：点击 Span → 右侧滑出详情，显示 input/output JSON、token 消耗、错误信息、metadata。

**Trace 回放**：点击"回放"→ 逐 Span 动画展示执行过程，显示每个节点的输入/输出，灰色已完成，绿色当前正在执行。

**统计仪表盘**：总调用次数、P50/P95/P99 延迟、成功率、Token 日消耗曲线、最慢插件 Top 5。

### 4.2 技术实现

- 前端复用 DDW 现有 React 仪表盘框架
- 瀑布图使用 vis-timeline（MIT）或自定义 Canvas 实现
- 实时更新通过 WebSocket 推送新的 Span 完成事件

---

## 五、配置

```yaml
name: ddw-trace-panel
version: 1.0.0
description: "完整 Trace 可观测性面板"
author: DDW Team
license: Apache-2.0
engine: ">=2.0.0"
isolation: inline

permissions:
  - "database:ddw_trace_panel"

dependencies:
  plugins:
    ddw-llm-gateway: ">=1.0.0"
  python:
    - fastapi>=0.110
    - sqlalchemy>=2.0
    - pydantic>=2.0

events:
  produces:
    - "trace.span.created"
    - "trace.span.completed"
  consumes:
    - "sop.node.executed"
    - "user.message.received"

config:
  optional:
    trace_retention_days: 30
    sampling_rate: 1.0
    max_spans_per_trace: 100
    enable_input_output_logging: true
    auto_purge_days: 30

ecosystem:
  category: "observability"
  tags: ["trace", "monitoring", "debugging"]
```

---



## X. 插件入口（DDW 规范要求）

### register(app) 注册函数

```python
# __init__.py
PLUGIN_NAME = "ddw-trace-panel"
PLUGIN_VERSION = "1.0.0"

def register(app, config=None):
    """DDW 平台调用此函数挂载插件路由。"""
    from .router import router
    app.include_router(
        router,
        prefix=f"/api/v1/plugins/{PLUGIN_NAME}",
        tags=[PLUGIN_NAME],
    )
```

### 标准健康检查端点

```python
# router.py 中必须包含
@router.get("/health")
async def health():
    return {
        "plugin": PLUGIN_NAME,
        "status": "ok",
        "version": PLUGIN_VERSION,
        "endpoints": ["/traces", "/stats/overview", "/stats/hotspots"],
    }
```

### 资源消耗声明（DDW 规范 §5.4）

| 维度 | 评估值 |
|:-----|:------|
| CPU 常态负载 | 5-10% |
| CPU 峰值负载 | 25% |
| 基础内存 | 64 MB |
| 运行时内存 | 128 MB |
| 峰值内存 | 256 MB |
| 代码体积 | 80 KB |
| 数据库存储 | 按使用量 |
| LLM Token | 走 DDW Gateway（不自配 Provider） |
| 必需依赖 | ddw-llm-gateway |
| 资源评级 | **轻量级/中等级** |

## 六、灵感溯源

- **灵感来源**：StaffDeck 的"执行记录审查"概念 + OpenTelemetry 分布式追踪标准
- **DDW 实现**：全新 Apache 2.0。Trace 数据模型兼容 OpenTelemetry Span 规范。上下文管理器使用 Python `contextlib.contextmanager` + `functools.wraps` 标准库，数据采集完全自主开发

---

*代码实现由 MiMo Code CLI 执行，DeepSeek V4 Flash 代码审查。SDK-2 (execution_trace) 需在插件开发前完成。*
