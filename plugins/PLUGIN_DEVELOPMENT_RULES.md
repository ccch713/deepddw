# DDW AI 底座平台插件开发规范

## 重要原则

**插件必须复用平台已有能力，不要重复造轮子。**

---

## 一、平台核心能力（插件必须复用）

### 1. LLM Gateway（已配置 minimax）

**位置**：`config/deployment.yaml`

```yaml
llm_gateway:
  default_provider: minimax
  providers:
    minimax:
      base_url: https://api.minimaxi.com/v1
      api_key: ${MINIMAX_API_KEY}
      default_model: MiniMax-M3
      timeout: 30
```

**插件应该**：
- 调用平台的 LLM Gateway，而不是自己实现 HTTP 调用
- 使用平台配置的 API Key 和模型
- 不要在插件里硬编码 API Key

**错误做法**：
```python
# ❌ 插件自己实现 LLM 调用
class LLMGateway:
    def __init__(self, config):
        self.api_key = config.get("api_key", "")  # 硬编码
        self.base_url = "https://api.minimaxi.com/v1"  # 硬编码
```

**正确做法**：
```python
# ✅ 复用平台的 LLM Gateway
from embedded_llm.engine import EmbeddedLLM

class CustomerServicePlugin:
    def __init__(self, app):
        # 使用平台的 LLM 引擎
        self.llm = EmbeddedLLM(...)
```

### 2. 知识库加载器（DDWKnowledgeBase）

**位置**：`embedded_llm/engine.py`

```python
class DDWKnowledgeBase:
    """加载 DDW 平台知识文件"""
    SUPPORTED_EXTS = {".yaml", ".yml", ".md", ".txt", ".json"}
    
    def __init__(self, knowledge_dir: str):
        # 自动加载目录下所有知识文件
        ...
    
    def as_system_prompt(self) -> str:
        # 生成 system prompt
        ...
```

**插件应该**：
- 使用 DDWKnowledgeBase 加载知识库
- 不要自己实现文件读取和解析

**错误做法**：
```python
# ❌ 插件自己实现知识库加载
class KnowledgeBaseManager:
    def __init__(self, knowledge_dir):
        self.chunks = []
        self._load_all()  # 重复实现
```

**正确做法**：
```python
# ✅ 复用平台的知识库
from embedded_llm.engine import DDWKnowledgeBase

class CustomerServicePlugin:
    def __init__(self, app):
        # 使用平台的知识库加载器
        self.knowledge = DDWKnowledgeBase("./knowledge")
```

### 3. 插件基类（PluginBase）

**位置**：`sdk/plugin_base.py`

```python
class PluginBase:
    """插件基类"""
    name: str = "unnamed-plugin"
    version: str = "0.1.0"
    router_prefix: str = ""
    
    def __init__(self, app: FastAPI, config=None, manifest=None):
        self.app = app
        self.config = ConfigManager(self.name, defaults=config)
        self.router = APIRouter(prefix=self.router_prefix)
        self.setup()
    
    def setup(self):
        """钩子函数，子类重写"""
        pass
    
    def register(self):
        """注册路由到平台"""
        self.app.include_router(self.router)
```

**插件必须**：
- 继承 PluginBase
- 重写 setup() 方法
- 使用 self.config 获取配置
- 使用 self.router 注册路由

### 4. 配置管理器（ConfigManager）

**位置**：`sdk/config_manager.py`

```python
class ConfigManager:
    """配置管理器"""
    def __init__(self, plugin_name, defaults=None):
        self._defaults = defaults or {}
        self._overrides = {}
    
    def get(self, key, default=None):
        """获取配置（优先级：overrides > defaults）"""
        ...
```

**插件应该**：
- 通过 self.config.get("key") 获取配置
- 不要自己读取配置文件

### 5. 工具定义规范（ToolDefinition）

**位置**：`sdk/tool_def.py`

```python
@dataclass
class ToolDefinition:
    name: str  # 必须以 "ddw." 开头
    description: str  # ≤250 字符
    parameters: list[ParamDef]
    required_permissions: list[str]
```

**插件工具必须**：
- 名称以 `ddw.` 开头
- 描述不超过 250 字符
- 声明所需权限

---

## 二、客服插件问题分析

### 当前问题

| 问题 | 说明 | 严重程度 |
|---|---|---|
| 自己实现 LLMGateway | 重复造轮子 | 🔴 高 |
| 自己实现 KnowledgeBaseManager | 重复造轮子 | 🔴 高 |
| 没有继承 PluginBase | 不符合规范 | 🔴 高 |
| 没有使用 ConfigManager | 不符合规范 | 🟡 中 |
| 硬编码 API Key | 安全风险 | 🔴 高 |
| 硬编码 base_url | 维护困难 | 🟡 中 |

### 对比

| 功能 | 当前实现 | 平台提供 | 应该 |
|---|---|---|---|
| LLM 调用 | 自己实现 | ✅ EmbeddedLLM | 复用平台 |
| 知识库加载 | 自己实现 | ✅ DDWKnowledgeBase | 复用平台 |
| 配置管理 | 自己实现 | ✅ ConfigManager | 复用平台 |
| 插件注册 | 手动注册 | ✅ PluginBase.register() | 继承基类 |
| 路由管理 | 手动创建 | ✅ self.router | 使用基类 |

---

## 三、插件开发规范

### 1. 目录结构

```
plugins/my-plugin/
├── __init__.py          # 插件主逻辑（必须）
├── manifest.yaml        # 插件配置（必须）
├── knowledge/           # 知识库目录（可选）
├── widget/              # 前端组件（可选）
├── templates/           # 模板文件（可选）
└── tests/               # 测试文件（可选）
```

### 2. manifest.yaml 规范

```yaml
name: my-plugin
version: 1.0.0
description: 插件描述

# 插件配置（通过 ConfigManager 管理）
config:
  # 业务配置
  business:
    key: value
  
  # LLM 配置（如果需要特殊配置）
  llm:
    model: MiniMax-M3  # 可选，覆盖平台默认
    temperature: 0.7

# 权限声明
permissions:
  - filesystem  # 读取文件
  - network    # 网络请求
  - compute    # 计算资源

# 依赖
dependencies: []
```

### 3. __init__.py 规范

```python
"""插件描述"""

from __future__ import annotations
import logging
from typing import Any

from fastapi import APIRouter
from sdk.plugin_base import PluginBase

logger = logging.getLogger(__name__)

class MyPlugin(PluginBase):
    """插件主类（必须继承 PluginBase）"""
    
    name = "my-plugin"
    version = "1.0.0"
    router_prefix = "/api/v1/plugins/my-plugin"
    
    def setup(self):
        """初始化（重写基类方法）"""
        # 1. 获取配置
        business_config = self.config.get("business", {})
        
        # 2. 复用平台能力
        from embedded_llm.engine import EmbeddedLLM, DDWKnowledgeBase
        self.llm = EmbeddedLLM(...)
        self.knowledge = DDWKnowledgeBase("./knowledge")
        
        # 3. 注册路由
        self._register_routes()
    
    def _register_routes(self):
        """注册路由"""
        @self.router.get("/health")
        async def health():
            return {"plugin": self.name, "status": "ok"}
        
        @self.router.post("/chat")
        async def chat(request: ChatRequest):
            # 使用平台的 LLM 和知识库
            system_prompt = self.knowledge.as_system_prompt()
            answer = await self.llm.chat(request.message, system_prompt)
            return {"answer": answer}

def register(app: Any) -> None:
    """注册插件（必须提供）"""
    plugin = MyPlugin(app)
    plugin.register()
    logger.info("My Plugin registered")
```

### 4. 禁止事项

| 禁止 | 原因 |
|---|---|
| ❌ 自己实现 LLM 调用 | 应复用平台 LLM Gateway |
| ❌ 自己实现知识库加载 | 应复用 DDWKnowledgeBase |
| ❌ 硬编码 API Key | 应使用平台配置 |
| ❌ 硬编码 base_url | 应使用平台配置 |
| ❌ 不继承 PluginBase | 必须继承基类 |
| ❌ 不使用 ConfigManager | 必须使用配置管理器 |
| ❌ 工具名不以 ddw. 开头 | 必须遵循命名规范 |
| ❌ 描述超过 250 字符 | 必须遵循长度限制 |

### 5. 必须事项

| 必须 | 说明 |
|---|---|
| ✅ 继承 PluginBase | 插件基类 |
| ✅ 重写 setup() | 初始化逻辑 |
| ✅ 提供 register(app) | 注册函数 |
| ✅ 使用 self.config | 配置管理 |
| ✅ 使用 self.router | 路由管理 |
| ✅ 复用平台 LLM | 不要重复造轮子 |
| ✅ 复用平台知识库 | 不要重复造轮子 |
| ✅ 声明权限 | manifest.yaml |

---

## 四、客服插件优化方案

### 需要删除的代码

1. `LLMGateway` 类 → 使用 `EmbeddedLLM`
2. `KnowledgeBaseManager` 类 → 使用 `DDWKnowledgeBase`
3. 硬编码的 API Key 和 base_url → 使用平台配置

### 需要新增的代码

1. 继承 `PluginBase`
2. 使用 `self.config` 获取配置
3. 使用 `self.llm` 调用平台 LLM
4. 使用 `self.knowledge` 加载知识库

### 优化后的架构

```
客服插件
├── __init__.py
│   ├── CustomerServicePlugin(PluginBase)  # 继承基类
│   │   ├── setup()                        # 初始化
│   │   ├── _register_routes()             # 注册路由
│   │   └── _chat()                        # 业务逻辑
│   └── register(app)                      # 注册函数
├── manifest.yaml                          # 配置
├── knowledge/                             # 知识库
└── widget/                                # 前端组件
```

### 依赖关系

```
客服插件
    ↓
┌─────────────────────────────┐
│  DDW AI 底座平台             │
│  ├── PluginBase             │
│  ├── ConfigManager          │
│  ├── EmbeddedLLM            │
│  ├── DDWKnowledgeBase       │
│  └── LLM Gateway (minimax)  │
└─────────────────────────────┘
```

---

## 五、测试验证

### 1. 语法检查

```bash
python -m py_compile plugins/my-plugin/__init__.py
```

### 2. 导入检查

```python
from plugins.my-plugin import register
```

### 3. 功能测试

```bash
ddw server start
curl http://localhost:8500/api/v1/plugins/my-plugin/health
```

---

## 六、版本管理

| 版本 | 说明 |
|---|---|
| 1.0.0 | 初版（不符合规范） |
| 1.1.0 | 符合规范版本 |
| 2.0.0 | 完全复用平台能力 |

---

**最后更新**：2026-07-12  
**维护者**：DDW AI Team
