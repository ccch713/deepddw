# DDW LLM Gateway 插件

LLM 统一网关插件，提供 51 种渠道类型支持、负载均衡、断路器、流式 SSE 转发。

## 核心特性

- **51 种渠道类型**：完整映射 One API 渠道类型，支持国内外主流 LLM 厂商
- **负载均衡**：优先级 + 加权随机 + 成功率过滤，三阶段筛选
- **断路器**：连续失败自动禁用，定时重测自动恢复
- **流式 SSE**：异步流式转发，支持 Token 计量
- **OpenAI 兼容**：标准化请求/响应格式

## 目录结构

```
ddw-llm-gateway/
├── manifest.yaml           # 插件元数据
├── __init__.py             # 插件入口（register 函数）
├── main.py                 # 插件主类（继承 PluginBase）
├── models.py               # SQLAlchemy 数据模型
├── channel_types.py        # 51 种渠道类型枚举
├── channel_manager.py      # 渠道管理（CRUD + 状态管理）
├── load_balancer.py        # 负载均衡引擎
├── circuit_breaker.py      # 断路器
├── relay.py                # 请求转发核心
├── stream_handler.py       # 流式 SSE 处理
├── health_monitor.py       # 渠道健康监控
├── config_loader.py        # YAML 配置加载
├── router.py               # FastAPI 路由
├── config/
│   └── channels.yaml       # 示例渠道配置
├── tests/                  # 测试目录
│   ├── test_load_balancer.py
│   ├── test_circuit_breaker.py
│   ├── test_channel_manager.py
│   └── test_relay.py
├── requirements.txt        # Python 依赖
└── README.md               # 本文档
```

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行测试

```bash
pytest tests/ -v
```

### 配置渠道

编辑 `config/channels.yaml`，添加你的 LLM 渠道：

```yaml
channels:
  - name: "my-channel"
    type: 1                     # ChannelType.OPENAI
    base_url: "https://api.openai.com/v1"
    api_keys:
      - "sk-${MY_API_KEY}"     # 支持环境变量
    models:
      - "gpt-4o"
    priority: 10
    weight: 100
```

## API 端点

### OpenAI 兼容端点

| 端点 | 方法 | 说明 |
|:-----|:-----|:-----|
| `/v1/chat/completions` | POST | Chat Completion 转发 |
| `/v1/completions` | POST | Text Completion 转发 |
| `/v1/embeddings` | POST | Embedding 转发 |
| `/v1/images/generations` | POST | 图像生成转发 |
| `/v1/models` | GET | 可用模型列表 |

### 管理端点

| 端点 | 方法 | 说明 |
|:-----|:-----|:-----|
| `/api/gateway/channels` | GET | 渠道列表 |
| `/api/gateway/channels` | POST | 创建渠道 |
| `/api/gateway/channels/{id}` | PUT | 更新渠道 |
| `/api/gateway/channels/{id}` | DELETE | 删除渠道 |
| `/api/gateway/channels/{id}/test` | POST | 测试渠道 |
| `/api/gateway/channels/test-all` | POST | 批量测试 |
| `/api/gateway/dashboard` | GET | Dashboard |

## 架构设计

### 负载均衡三阶段筛选

1. **基础过滤**：成功率 > 阈值 + 余额 > 0
2. **优先级分组**：选择最高优先级组
3. **加权随机**：同优先级内按权重随机选择

### 断路器规则

1. 连续失败 ≥ 5 次 → 自动禁用渠道
2. 禁用后每 300 秒自动测试
3. 测试成功 → 恢复启用
4. 成功率 < 50% → 被负载均衡器过滤

### 流式 SSE 转发

```
客户端 → Gateway → 上游 LLM
       ← SSE 流 ←
```

支持 Token 计量：流式结束后根据 usage 信息后置计费。

## 与 ddw-token-manager 集成

### 预消费（请求前）

```python
result = await token_manager.pre_consume(user_id=1, model="gpt-4o")
if not result["allowed"]:
    return 429  # 额度不足
```

### 后消费（请求后）

```python
await token_manager.post_consume(
    user_id=1,
    channel_id=1,
    model="gpt-4o",
    prompt_tokens=100,
    completion_tokens=200,
)
```

## 配置说明

### 环境变量替换

在 `channels.yaml` 中使用 `${VAR_NAME}` 引用环境变量：

```yaml
api_keys:
  - "sk-${OPENAI_KEY}"
```

运行时自动替换为环境变量的值。

### 渠道类型

完整列表见 `channel_types.py`，包含 51 种渠道类型：

| 类型 | 值 | 说明 |
|:-----|:---|:-----|
| OPENAI | 1 | OpenAI GPT 系列 |
| DEEPSEEK | 24 | DeepSeek |
| MINIMAX | 25 | MiniMax |
| OLLAMA | 11 | Ollama 本地 |
| ... | ... | ... |

## 开发指南

### 添加新渠道类型

1. 在 `channel_types.py` 的 `ChannelType` 枚举中添加新值
2. 在 `CHANNEL_TYPE_REGISTRY` 中添加元数据
3. 在 `config/channels.yaml` 中添加配置示例

### 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试
pytest tests/test_load_balancer.py -v

# 生成覆盖率报告
pytest tests/ --cov=. --cov-report=html
```

## License

MIT
