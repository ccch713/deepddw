# DDW AI Hub 插件开发指南

> **DDW AI Hub 插件开发指南 v1.0** | 2026-07-12 | 适用于 DDW v2.0+
>
> 面向企业 IT 人员和独立开发者的完整插件开发参考文档

---

## 目录

1. [概述](#1-概述)
2. [快速开始](#2-快速开始)
3. [插件架构详解](#3-插件架构详解)
4. [manifest.yaml 完整规范](#4-manifestyaml-完整规范)
5. [数据库集成](#5-数据库集成)
6. [API 端点开发](#6-api-端点开发)
7. [事件系统](#7-事件系统)
8. [配置管理](#8-配置管理)
9. [测试指南](#9-测试指南)
10. [打包与发布](#10-打包与发布)
11. [完整示例](#11-完整示例)
12. [最佳实践](#12-最佳实践)
13. [常见问题](#13-常见问题)
14. [附录](#14-附录)

---

## 1. 概述

### 1.1 DDW 插件是什么

DDW 插件是 DDW AI Hub 平台的扩展单元，以 Python 包的形式封装业务逻辑、API 端点和事件处理。每个插件通过 `manifest.yaml` 声明元数据、依赖和权限，由平台的 `PluginManager` 统一发现、注册和管理。

插件在平台进程内运行（`inline` 模式）或在独立沙箱进程中隔离运行（`process` 模式），通过 FastAPI `APIRouter` 暴露 HTTP 端点，通过 `EventBus` 参与平台事件系统。

### 1.2 插件能做什么

| 用例 | 说明 |
|------|------|
| **业务系统集成** | 将诊所管理、CRM、ERP 等现有系统封装为标准化 API（参考 `oral-clinic` 插件） |
| **数据处理管道** | 对接外部数据源，执行 ETL 任务，发布处理结果事件 |
| **LLM 工具注册** | 为 AI Agent 注册新的工具（Tool），通过 `ToolDefinition` 声明参数和权限 |
| **第三方服务对接** | 封装微信、飞书、钉钉等平台 API，提供统一的回调和消息处理 |
| **运营自动化** | 邮件自动回复、社交媒体排期、SEO 优化等运营场景（参考 `operations` 插件） |

### 1.3 开发前置条件

- **Python 3.11+**（推荐 3.12）
- **pip** 用于安装依赖
- **DDW AI Hub** 平台已部署并可运行（local-llm 或 cloud-llm 模式）
- 基本的 **FastAPI** 和 **SQLAlchemy** 知识
- 熟悉 **YAML** 格式（编写 manifest）

---

## 2. 快速开始

### 2.1 从模板创建第一个插件

```bash
# 进入 DDW 平台插件目录
cd ddw-ai-hub/plugins/

# 从模板复制
cp -r _template/ hello-world/

# 编辑 manifest.yaml
cd hello-world/
```

修改 `manifest.yaml`：

```yaml
name: hello-world
version: 1.0.0
description: "我的第一个 DDW 插件"
author: "Your Name"
license: "MIT"
engine: ">=2.0.0"
isolation: inline
```

创建 `__init__.py`：

```python
"""Hello World 插件 — DDW AI Hub 入门示例."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

PLUGIN_NAME = "hello-world"
PLUGIN_PREFIX = f"/api/v1/plugins/{PLUGIN_NAME}"

router = APIRouter(tags=[PLUGIN_NAME])


@router.get("/health")
async def health() -> dict[str, Any]:
    """健康检查端点。"""
    return {"plugin": PLUGIN_NAME, "status": "ok"}


@router.get("/greet")
async def greet(name: str = "World") -> dict[str, Any]:
    """问候端点。"""
    return {"message": f"Hello, {name}!"}


def register(app, config: dict[str, Any] | None = None) -> None:
    """平台调用此函数挂载插件路由。"""
    app.include_router(router, prefix=PLUGIN_PREFIX, tags=[PLUGIN_NAME])
    logger.info("hello-world plugin registered (api=%s)", PLUGIN_PREFIX)
```

### 2.2 目录结构说明

```
hello-world/
├── manifest.yaml          # 必须：插件元数据
├── __init__.py            # 必须：暴露 register(app) 函数
├── api.py                 # 可选：API 路由模块
├── models.py              # 可选：SQLAlchemy ORM 模型
├── db.py                  # 可选：数据库初始化
├── services.py            # 可选：业务逻辑
├── locales/               # 可选：国际化
│   ├── zh-CN.json
│   └── en.json
└── tests/                 # 可选：测试
    ├── __init__.py
    ├── conftest.py
    └── test_api.py
```

### 2.3 manifest.yaml 必填字段

```yaml
name: hello-world        # 小写字母 + 连字符，全局唯一
version: 1.0.0           # 语义化版本（SemVer）
description: "一句话描述"  # ≤200 字符
author: "作者名"
license: "MIT"
```

### 2.4 本地测试

```bash
# 启动 DDW 平台（插件会自动发现）
cd ddw-ai-hub/
python -m core.main

# 测试健康检查
curl http://localhost:8000/api/v1/plugins/hello-world/health
# → {"plugin":"hello-world","status":"ok"}

# 测试业务端点
curl "http://localhost:8000/api/v1/plugins/hello-world/greet?name=DDW"
# → {"message":"Hello, DDW!"}
```

### 2.5 打包发布

```bash
# 使用打包脚本
cd ddw-ai-hub/local-llm/
bash scripts/package_plugin.sh ./plugins/hello-world/

# 生成文件: hello-world_1.0.0.ddwplugin
```

---

## 3. 插件架构详解

### 3.1 PluginBase 基类

DDW 平台提供两种插件基类，适用于不同部署模式：

#### 3.1.1 inline 模式基类（推荐）

用于可信插件，在平台进程内直接导入运行：

```python
from sdk.plugin_base import PluginBase

class MyPlugin(PluginBase):
    name = "my-plugin"
    version = "0.1.0"
    router_prefix = ""  # 自动设为 /api/v1/plugins/my-plugin

    def setup(self) -> None:
        """声明路由、订阅事件等。"""
        self.get("/health")(self.health)
        self.post("/process")(self.process)

    async def health(self):
        return {"status": "ok", "plugin": self.name}
```

**完整 API 列表：**

| 方法 | 说明 |
|------|------|
| `__init__(app, config, manifest)` | 构造函数，接收 FastAPI app、配置和 manifest |
| `setup()` | 子类重写此方法，注册路由和事件 |
| `add_route(path, **kwargs)` | 在 `self.router` 上声明 GET 路由 |
| `get(path, **kwargs)` | 在 `self.router` 上声明 GET 路由（快捷方式） |
| `post(path, **kwargs)` | 在 `self.router` 上声明 POST 路由 |
| `register()` | 将 `self.router` 挂载到宿主 app |

**属性：**

| 属性 | 类型 | 说明 |
|------|------|------|
| `self.app` | `FastAPI` | 宿主 FastAPI 实例 |
| `self.manifest` | `dict` | 解析后的 manifest.yaml |
| `self.config` | `ConfigManager` | 配置管理器实例 |
| `self.router` | `APIRouter` | 插件专用路由 |

#### 3.1.2 ABC 模式基类（legacy）

用于需要严格实现生命周期接口的场景：

```python
from sdk.plugin_base import DDWPlugin

class MyPlugin(DDWPlugin):
    def __init__(self, name, version, manifest):
        super().__init__(name, version, manifest)

    def on_install(self) -> None:
        """安装时调用：创建数据库表、初始化配置。"""
        pass

    def on_enable(self) -> None:
        """启用时调用：验证配置、注册路由、启动服务。"""
        pass

    def on_disable(self) -> None:
        """禁用时调用：清理资源、停止后台任务。"""
        pass

    def on_uninstall(self) -> None:
        """卸载时调用：删除数据库表、清理配置。"""
        pass

    def get_config(self, key: str) -> Any:
        """获取配置值。"""
        return self.config.get(key)

    def get_db_session(self):
        """获取数据库会话。"""
        raise NotImplementedError

    def publish_event(self, event: dict) -> None:
        """发布事件到平台。"""
        raise NotImplementedError

    def register_api(self, router: APIRouter) -> None:
        """注册额外的 API 路由。"""
        self.router.include_router(router)
```

### 3.2 插件生命周期状态机

每个插件由 `PluginStateInfo` 追踪其状态，共 5 种状态：

```
                    ┌─────────────┐
                    │   LOADING   │
                    │  (加载中)    │
                    └──────┬──────┘
                           │ 成功
                           ▼
                    ┌─────────────┐
            ┌──────│   ACTIVE    │──────┐
            │      │  (运行中)    │      │
            │      └──────┬──────┘      │
            │             │             │
       禁用 │        出错 │        版本过期│
            ▼             ▼             ▼
     ┌──────────┐  ┌──────────┐  ┌──────────┐
     │ DISABLED │  │  FAILED  │  │NEEDS_UPDATE│
     │ (已禁用)  │  │ (失败)    │  │ (需更新)   │
     └──────────┘  └──────────┘  └──────────┘
            │             │
            │  重试(≤5次)  │
            └──────┬──────┘
                   ▼
            ┌─────────────┐
            │   LOADING   │
            └─────────────┘
```

**状态说明：**

| 状态 | 说明 | 关键字段 |
|------|------|----------|
| `LOADING` | 正在加载/初始化 | `started_at`, `attempt_count`（最多 5 次重试） |
| `ACTIVE` | 正常运行 | `loaded_at`, `capabilities` |
| `FAILED` | 加载/运行出错 | `error_code`, `error_message` |
| `DISABLED` | 被管理员/用户禁用 | `disabled_by`（user/system/admin）, `reason` |
| `NEEDS_UPDATE` | 有新版本可用 | `current_version`, `available_version` |

**状态转换方法：**

```python
from sdk.plugin_state import PluginStateInfo

info = PluginStateInfo(state=PluginState.LOADING, name="my-plugin", version="1.0.0")

info.to_loading()                        # → LOADING，attempt_count +1
info.to_active()                         # → ACTIVE，重置 attempt_count
info.to_failed(5001, "connection timeout") # → FAILED，记录错误码
info.to_disabled("admin", "not needed")  # → DISABLED
info.to_needs_update("1.2.0")            # → NEEDS_UPDATE

info.can_retry()  # → attempt_count < max_attempts (5)
```

### 3.3 进程内 vs 沙箱隔离

| 模式 | `isolation` 值 | 说明 | 适用场景 |
|------|----------------|------|----------|
| **进程内** | `inline` | 插件代码直接在平台进程内 import 运行 | 可信插件、高性能要求 |
| **沙箱** | `process` | 插件在独立子进程中运行，通过 JSON-RPC 通信 | 第三方不可信插件 |

**沙箱模式特性：**

- 通过 `SandboxPolicy` 声明资源限制（CPU 时间、内存、网络、文件系统）
- 使用 `JSONRPCBridge` 进行进程间通信
- 支持三段式信号关闭（SIGINT → SIGTERM → SIGKILL）

```yaml
# manifest.yaml 中声明沙箱模式
isolation: process
permissions:
  - network    # 允许网络访问
  - storage    # 允许文件系统访问
```

### 3.4 事件系统

平台提供进程内 `EventBus`，支持 pub/sub 模式：

- **精确匹配**：`subscribe("user.registered", handler)`
- **通配符**：`subscribe("user.*", handler)` 匹配 `user.created`、`user.deleted` 等
- **并发分发**：多个订阅者并行执行，单个失败不影响其他

详见 [第 7 章 事件系统](#7-事件系统)。

---

## 4. manifest.yaml 完整规范

### 4.1 必填字段

```yaml
name: my-plugin             # 小写字母 + 连字符，全局唯一，≤64 字符
version: 1.0.0              # 语义化版本（SemVer 2.0）
description: "一句话描述"    # ≤200 字符
author: "作者名"
license: "MIT"
```

### 4.2 可选字段

```yaml
# 平台版本要求
engine: ">=2.0.0"           # 最低 DDW 平台版本

# 隔离模式
isolation: inline           # inline（默认）| process

# 权限声明
permissions:
  - network                 # 网络访问（调用外部 API）
  - storage                 # 文件系统读写
  - "database:my_plugin"    # 数据库访问（限定命名空间）
  - "api:some:read"         # API 访问（限定资源和操作）

# 配置项
config:
  required:                 # 必填配置
    - api_key
    - database_url
  optional:                 # 可选配置（含默认值）
    timeout: 30
    retries: 3
    debug: false

# 依赖
dependencies:
  plugins:                  # 其他插件依赖（支持版本约束）
    dingtalk_adapter: ">=1.0.0"
  python:                   # pip 依赖
    - requests>=2.25.0
    - pydantic>=2.0
    - sqlalchemy>=2.0

# 事件声明
events:
  produces:                 # 本插件发布的事件
    - "data.created"
    - "data.updated"
  consumes:                 # 本插件监听的事件
    - "user.registered"

# AI 质量标准（可选，用于 LLM 输出类插件）
quality:
  ai_output:
    required: false
    eval_spec: "eval.yaml"
    max_hallucination_rate: 0.05
    min_consistency_score: 0.80

# 试用期（可选，用于市场分发）
trial:
  enabled: true
  duration_days: 14

# 生态（可选）
ecosystem:
  category: "business"
  tags: ["crm", "medical"]
  icon: "assets/icon.png"
```

### 4.3 字段速查表

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | string | ✅ | — | 插件名，小写+连字符 |
| `version` | string | ✅ | — | SemVer 版本 |
| `description` | string | ✅ | — | 一句话描述 |
| `author` | string | ✅ | — | 作者 |
| `license` | string | ✅ | — | 开源协议 |
| `engine` | string | — | `>=0.1.0` | 最低平台版本 |
| `isolation` | string | — | `inline` | 隔离模式 |
| `permissions` | list | — | `[]` | 权限列表 |
| `config` | object | — | `{}` | 配置项定义 |
| `dependencies` | object | — | `{}` | 依赖声明 |
| `events` | object | — | `{}` | 事件声明 |
| `quality` | object | — | — | AI 质量标准 |
| `trial` | object | — | — | 试用期配置 |
| `ecosystem` | object | — | — | 市场分类信息 |

---

## 5. 数据库集成

### 5.1 使用 SQLAlchemy 2.x + asyncpg

DDW 推荐使用 SQLAlchemy 2.x 异步引擎连接 PostgreSQL：

```python
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """ORM 声明基类。"""


class MyModel(Base):
    __tablename__ = "my_table"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    data: Mapped[dict | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
```

### 5.2 数据库初始化

```python
_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


async def init_db(
    engine: AsyncEngine | None = None,
    database_url: str | None = None,
    create_tables: bool = True,
) -> AsyncEngine:
    """初始化数据库引擎（幂等）。"""
    global _engine, _session_maker

    if engine is not None:
        _engine = engine
    elif _engine is None:
        url = database_url or os.environ.get(
            "MY_PLUGIN_DATABASE_URL",
            "postgresql+asyncpg://user:pass@127.0.0.1:5432/my_plugin",
        )
        _engine = create_async_engine(
            url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )

    if _session_maker is None:
        _session_maker = async_sessionmaker(
            bind=_engine, expire_on_commit=False
        )

    if create_tables and _engine is not None:
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    return _engine


def session_maker() -> async_sessionmaker[AsyncSession]:
    """获取全局 Session 工厂。"""
    if _session_maker is None:
        raise RuntimeError("调用 init_db() 后才能使用 session_maker()")
    return _session_maker
```

### 5.3 在路由中使用 Session

```python
from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _get_session() -> AsyncSession:
    async with session_maker()() as s:
        yield s


@router.get("", response_model=list[ItemOut])
async def list_items(db: AsyncSession = Depends(_get_session)):
    rows = (await db.execute(select(MyModel))).scalars().all()
    return [ItemOut.model_validate(r) for r in rows]


@router.post("", response_model=ItemOut, status_code=201)
async def create_item(payload: ItemIn, db: AsyncSession = Depends(_get_session)):
    item = MyModel(**payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return ItemOut.model_validate(item)
```

### 5.4 数据迁移策略

DDW 插件使用 `Base.metadata.create_all()` 在首次启动时自动建表。对于生产环境的 schema 变更：

1. **新增字段**：使用 `nullable=True` 或提供 `default` 值，确保向后兼容
2. **删除字段**：先发布一个版本停止使用该字段，下一版本再从 model 中移除
3. **重命名字段**：使用 `AlterColumn` 添加新列 → 迁移数据 → 移除旧列
4. **推荐工具**：`alembic` 管理生产数据库迁移

---

## 6. API 端点开发

### 6.1 FastAPI APIRouter 注册方式

```python
from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
async def list_users():
    ...


@router.post("", response_model=UserOut, status_code=201)
async def create_user(payload: UserIn):
    ...
```

在 `register()` 中挂载：

```python
def register(app, config=None):
    app.include_router(
        router,
        prefix=f"/api/v1/plugins/{PLUGIN_NAME}",
        tags=[PLUGIN_NAME],
    )
```

### 6.2 路由前缀约定

所有插件端点必须遵循以下前缀：

```
/api/v1/plugins/{plugin_name}/{resource}
```

**示例：**

| 端点 | 说明 |
|------|------|
| `GET /api/v1/plugins/my-plugin/health` | 健康检查 |
| `GET /api/v1/plugins/my-plugin/users` | 业务端点 |
| `POST /api/v1/plugins/my-plugin/users` | 创建资源 |

### 6.3 健康检查端点（必须）

每个插件**必须**暴露 `/health` 端点：

```python
@router.get("/health")
async def health() -> dict:
    return {
        "plugin": PLUGIN_NAME,
        "status": "ok",
        "version": PLUGIN_VERSION,
        "endpoints": ["/users", "/orders"],
    }
```

平台通过此端点监控插件存活状态。响应格式：

```json
{
    "plugin": "my-plugin",
    "status": "ok",
    "version": "1.0.0",
    "endpoints": ["/users", "/orders"]
}
```

`status` 可选值：`"ok"` | `"degraded"` | `"error"`

### 6.4 OpenAPI 文档自动生成

FastAPI 的 `APIRouter` 自动为每个端点生成 OpenAPI schema。访问：

```
http://localhost:8000/docs               # Swagger UI
http://localhost:8000/openapi.json       # OpenAPI JSON
```

插件的端点会自动归类到以插件名命名的 tag 下。

### 6.5 Pydantic 模型

使用 Pydantic v2 定义请求/响应模型：

```python
from pydantic import BaseModel, Field


class UserIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    email: str = Field(..., max_length=256)
    role: str = Field(default="viewer", pattern="^(admin|editor|viewer)$")


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    created_at: datetime
```

---

## 7. 事件系统

### 7.1 EventBus 概述

DDW 平台提供进程内 pub/sub 事件总线：

```python
from core.events.event_bus import Event, get_event_bus
```

**核心特性：**

- 异步分发（asyncio）
- 精确匹配 + 通配符（`*` 匹配单级）
- 并发执行，单个 handler 失败不影响其他
- 多 worker 部署时自动切换到 RedisEventBus

### 7.2 发布事件

```python
from core.events.event_bus import Event, get_event_bus


async def create_user(user_data: dict):
    # ... 创建用户逻辑 ...

    # 发布事件
    await get_event_bus().publish(
        Event(
            topic="user.registered",
            payload={"user_id": user.id, "email": user.email},
            sender="user-plugin",
        )
    )
```

### 7.3 监听事件

```python
from core.events.event_bus import Event, get_event_bus


async def on_user_registered(event: Event) -> None:
    """当用户注册时，发送欢迎邮件。"""
    user_id = event.payload["user_id"]
    # ... 发送欢迎邮件逻辑 ...


# 在插件 setup 中订阅
async def setup(self):
    bus = get_event_bus()
    await bus.subscribe("user.registered", on_user_registered)
    await bus.subscribe("user.*", on_user_any)  # 通配符匹配
```

### 7.4 事件格式

```python
@dataclass
class Event:
    topic: str              # 事件主题，如 "user.registered"
    payload: Any = None     # 事件负载（dict 或任意对象）
    sender: str | None = None  # 发送者标识
    correlation_id: str | None = None  # 关联 ID（用于链路追踪）
```

### 7.5 manifest.yaml 中声明事件

```yaml
events:
  produces:
    - "user.created"
    - "user.updated"
  consumes:
    - "order.completed"
    - "payment.processed"
```

这有助于平台进行依赖分析和事件路由优化。

---

## 8. 配置管理

### 8.1 ConfigManager 使用

```python
from sdk.config_manager import ConfigManager

# 由 PluginBase 自动创建，也可手动创建
config = ConfigManager("my-plugin", defaults={"timeout": 30})

# 读取配置
timeout = config.get("timeout")           # → 30
api_key = config.get("api_key", "")       # → "" (默认值)

# 获取全部配置（合并 defaults + overrides）
all_config = config.as_dict()

# 运行时更新覆盖
config.update({"timeout": 60, "retries": 5})
```

### 8.2 配置优先级

```
manifest.yaml defaults  ←  最低优先级
        ↓
数据库 stored config    ←  管理员通过 API 修改
        ↓
环境变量覆盖           ←  最高优先级
```

### 8.3 环境变量注入

平台支持通过环境变量覆盖插件配置：

```bash
# 环境变量命名约定：DDW_PLUGIN_{PLUGIN_NAME}_{KEY}
export DDW_PLUGIN_MY_PLUGIN_API_KEY="sk-xxx"
export DDW_PLUGIN_MY_PLUGIN_DATABASE_URL="postgresql+asyncpg://..."
```

### 8.4 配置变化检测

平台内置配置 hash 检测，配置变更时自动触发热重载：

```python
from sdk.config_hash import ConfigHashStore

store = ConfigHashStore()

# 监听配置变化
changed = await store.watch(
    "my-plugin",
    new_config,
    notifier=my_reload_handler,  # async (plugin_name, changes) -> None
)
```

---

## 9. 测试指南

### 9.1 pytest 测试框架

```python
# tests/conftest.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from my_plugin.db import Base, init_db


@pytest.fixture
async def db_engine():
    """使用 SQLite 内存数据库进行测试。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    await init_db(engine=engine, create_tables=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    """提供测试用 Session。"""
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker()() as session:
        yield session
```

### 9.2 mock DDW 环境

```python
# tests/test_api.py
from unittest.mock import AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    """创建测试用 FastAPI app。"""
    app = FastAPI()
    from my_plugin import register
    register(app, config={"database_url": "sqlite+aiosqlite:///:memory:"})
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_health(client):
    resp = client.get("/api/v1/plugins/my-plugin/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_item(client):
    resp = client.post(
        "/api/v1/plugins/my-plugin/items",
        json={"name": "Test Item"},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Test Item"
```

### 9.3 集成测试

```python
# tests/test_integration.py
import pytest
from core.events.event_bus import EventBus, Event


@pytest.mark.asyncio
async def test_event_publish():
    """测试事件发布和订阅。"""
    bus = EventBus()
    received = []

    async def handler(event: Event):
        received.append(event)

    await bus.subscribe("test.event", handler)
    await bus.publish(Event(topic="test.event", payload={"key": "value"}))

    assert len(received) == 1
    assert received[0].payload == {"key": "value"}
    await bus.close()
```

### 9.4 覆盖率要求

| 范围 | 最低覆盖率 |
|------|-----------|
| 核心业务逻辑 | ≥ 80% |
| API 端点 | ≥ 90% |
| 数据库操作 | ≥ 70% |
| 工具函数 | ≥ 85% |

运行覆盖率：

```bash
pytest --cov=my_plugin --cov-report=term-missing tests/
```

---

## 10. 打包与发布

### 10.1 package_plugin.sh 使用

```bash
cd ddw-ai-hub/local-llm/
bash scripts/package_plugin.sh ./plugins/my-plugin/
```

脚本执行流程：

1. 验证 `manifest.yaml` 存在且包含必填字段
2. 复制代码文件（排除隐藏文件和 `manifest.yaml`）
3. 复制 `locales/` 目录（如存在）
4. 计算所有文件的 SHA256 校验和
5. 创建 `{name}_{version}.ddwplugin` 压缩包（tar.gz）

### 10.2 .ddwplugin 格式

`.ddwplugin` 本质是 **tar.gz** 压缩包，包含：

```
my-plugin_1.0.0.ddwplugin/
├── manifest.yaml
├── __init__.py
├── api.py
├── models.py
├── checksums.txt          # 所有文件的 SHA256
└── locales/
    └── zh-CN.json
```

### 10.3 签名机制

打包脚本自动生成 `checksums.txt`，记录每个文件的 SHA256 校验和。平台安装时校验完整性：

```
a1b2c3d4...  manifest.yaml
e5f6g7h8...  __init__.py
i9j0k1l2...  api.py
```

### 10.4 市场上架流程

```bash
# 1. 打包
bash scripts/package_plugin.sh ./plugins/my-plugin/

# 2. 验证
ddw plugin info my-plugin
ddw plugin status my-plugin

# 3. 安装到本地测试
ddw plugin install ./my-plugin_1.0.0.ddwplugin

# 4. 发布到市场（Phase 2）
ddw plugin publish ./my-plugin_1.0.0.ddwplugin --market main
```

---

## 11. 完整示例

### 示例 1：Hello World

```python
"""Hello World — 最简 DDW 插件."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

PLUGIN_NAME = "hello-world"
PLUGIN_PREFIX = f"/api/v1/plugins/{PLUGIN_NAME}"

router = APIRouter(tags=[PLUGIN_NAME])


@router.get("/health")
async def health() -> dict[str, Any]:
    return {"plugin": PLUGIN_NAME, "status": "ok"}


@router.get("/greet")
async def greet(name: str = "World") -> dict[str, Any]:
    return {"message": f"Hello, {name}!"}


def register(app, config: dict[str, Any] | None = None) -> None:
    app.include_router(router, prefix=PLUGIN_PREFIX, tags=[PLUGIN_NAME])
    logger.info("hello-world plugin registered")
```

对应 `manifest.yaml`：

```yaml
name: hello-world
version: 1.0.0
description: "Hello World 示例插件"
author: "DDW Team"
license: "MIT"
isolation: inline
```

### 示例 2：天气查询插件

```python
"""天气查询插件 — 对接外部 OpenWeatherMap API."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

PLUGIN_NAME = "weather-query"
PLUGIN_PREFIX = f"/api/v1/plugins/{PLUGIN_NAME}"

router = APIRouter(tags=[PLUGIN_NAME])

# ── 配置 ──────────────────────────────────────────────────────────────

API_BASE = "https://api.openweathermap.org/data/2.5"
DEFAULT_TIMEOUT = 10  # 秒


def _get_api_key(config: dict | None = None) -> str:
    cfg = config or {}
    return cfg.get("api_key") or os.environ.get("OPENWEATHER_API_KEY", "")


def _get_units(config: dict | None = None) -> str:
    cfg = config or {}
    return cfg.get("units", "metric")


# ── Pydantic 模型 ──────────────────────────────────────────────────────

class WeatherResponse(BaseModel):
    city: str
    temperature: float = Field(..., description="温度（℃ 或 ℉）")
    humidity: int = Field(..., description="湿度百分比")
    description: str = Field(..., description="天气描述")
    wind_speed: float = Field(..., description="风速 m/s")
    icon: str = Field(default="", description="天气图标代码")


class ForecastDay(BaseModel):
    date: str
    temp_high: float
    temp_low: float
    description: str
    pop: float = Field(..., description="降水概率 0-1")


class ForecastResponse(BaseModel):
    city: str
    forecasts: list[ForecastDay]


# ── API 端点 ────────────────────────────────────────────────────────────

@router.get("/health")
async def health() -> dict[str, Any]:
    return {"plugin": PLUGIN_NAME, "status": "ok"}


@router.get("/current", response_model=WeatherResponse)
async def get_current_weather(
    city: str,
    config: dict[str, Any] | None = None,
) -> WeatherResponse:
    """查询指定城市的当前天气。"""
    api_key = _get_api_key(config)
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENWEATHER_API_KEY 未配置")

    units = _get_units(config)
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(
            f"{API_BASE}/weather",
            params={"q": city, "appid": api_key, "units": units},
        )
        if resp.status_code == 404:
            raise HTTPException(status_code=404, detail=f"城市 '{city}' 未找到")
        resp.raise_for_status()
        data = resp.json()

    main = data.get("main", {})
    weather = data.get("weather", [{}])[0]
    wind = data.get("wind", {})

    return WeatherResponse(
        city=data.get("name", city),
        temperature=main.get("temp", 0),
        humidity=main.get("humidity", 0),
        description=weather.get("description", ""),
        wind_speed=wind.get("speed", 0),
        icon=weather.get("icon", ""),
    )


@router.get("/forecast", response_model=ForecastResponse)
async def get_forecast(
    city: str,
    days: int = 5,
    config: dict[str, Any] | None = None,
) -> ForecastResponse:
    """查询未来 N 天天气预报。"""
    api_key = _get_api_key(config)
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENWEATHER_API_KEY 未配置")

    units = _get_units(config)
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        resp = await client.get(
            f"{API_BASE}/forecast",
            params={"q": city, "appid": api_key, "units": units, "cnt": days * 8},
        )
        resp.raise_for_status()
        data = resp.json()

    forecasts = []
    for item in data.get("list", [])[: days * 8 : 8]:
        forecasts.append(
            ForecastDay(
                date=item["dt_txt"][:10],
                temp_high=item["main"]["temp_max"],
                temp_low=item["main"]["temp_min"],
                description=item["weather"][0].get("description", ""),
                pop=item.get("pop", 0),
            )
        )

    return ForecastResponse(city=data.get("city", {}).get("name", city), forecasts=forecasts)


# ── 注册入口 ────────────────────────────────────────────────────────────

_config: dict[str, Any] | None = None


def register(app, config: dict[str, Any] | None = None) -> None:
    global _config
    _config = config or {}
    app.include_router(router, prefix=PLUGIN_PREFIX, tags=[PLUGIN_NAME])
    logger.info("weather-query plugin registered (api=%s)", PLUGIN_PREFIX)
```

对应 `manifest.yaml`：

```yaml
name: weather-query
version: 1.0.0
description: "天气查询插件，对接 OpenWeatherMap API"
author: "DDW Team"
license: "MIT"
isolation: inline
permissions:
  - network
config:
  required:
    - api_key
  optional:
    units: "metric"
dependencies:
  python:
    - httpx>=0.27.0
events:
  produces:
    - "weather.fetched"
```

### 示例 3：LLM Token Manager 插件

这是一个包含数据库、事件和定时任务的完整插件骨架：

```python
"""LLM Token Manager — 令牌用量追踪和限额管理插件.

功能：
- 追踪每个用户/Agent 的 LLM token 消耗
- 设置和查询配额（每日/每月）
- 发布用量告警事件
- 定时汇总报告
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

logger = logging.getLogger(__name__)

PLUGIN_NAME = "token-manager"
PLUGIN_PREFIX = f"/api/v1/plugins/{PLUGIN_NAME}"

# ── ORM 模型 ──────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class TokenUsage(Base):
    """单次 LLM 调用的 token 用量记录。"""
    __tablename__ = "token_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    endpoint: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )


class Quota(Base):
    """用户配额配置。"""
    __tablename__ = "quotas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    daily_limit_tokens: Mapped[int] = mapped_column(Integer, default=100_000)
    monthly_limit_usd: Mapped[float] = mapped_column(Float, default=50.0)
    daily_used_tokens: Mapped[int] = mapped_column(Integer, default=0)
    monthly_used_usd: Mapped[float] = mapped_column(Float, default=0.0)
    last_reset_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class AlertRule(Base):
    """告警规则。"""
    __tablename__ = "alert_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    threshold_percent: Mapped[int] = mapped_column(Integer, default=80)
    alert_type: Mapped[str] = mapped_column(String(32), default="daily")  # daily|monthly
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


# ── 数据库引擎 ────────────────────────────────────────────────────────

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


async def init_db(
    engine: AsyncEngine | None = None,
    database_url: str | None = None,
    create_tables: bool = True,
) -> AsyncEngine:
    global _engine, _session_maker

    if engine is not None:
        _engine = engine
    elif _engine is None:
        url = database_url or os.environ.get(
            "TOKEN_MANAGER_DATABASE_URL",
            "postgresql+asyncpg://ddw:ddw@127.0.0.1:5432/token_manager",
        )
        is_sqlite = url.startswith("sqlite")
        kwargs: dict = {"echo": False}
        if not is_sqlite:
            kwargs.update({"pool_size": 5, "max_overflow": 10, "pool_pre_ping": True})
        _engine = create_async_engine(url, **kwargs)

    if _session_maker is None:
        _session_maker = async_sessionmaker(bind=_engine, expire_on_commit=False)

    if create_tables and _engine is not None:
        async with _engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    return _engine


def session_maker() -> async_sessionmaker[AsyncSession]:
    if _session_maker is None:
        raise RuntimeError("调用 init_db() 后才能使用 session_maker()")
    return _session_maker


# ── Pydantic 模型 ──────────────────────────────────────────────────────

class UsageRecordIn(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    model: str = Field(..., min_length=1, max_length=64)
    input_tokens: int = Field(ge=0, default=0)
    output_tokens: int = Field(ge=0, default=0)
    total_cost_usd: float = Field(ge=0, default=0.0)
    endpoint: str = Field(default="")


class UsageSummary(BaseModel):
    user_id: str
    daily_tokens_used: int
    daily_limit: int
    daily_percent: float
    monthly_usd_used: float
    monthly_limit: float
    monthly_percent: float
    is_active: bool


class QuotaIn(BaseModel):
    daily_limit_tokens: int = Field(ge=1000, default=100_000)
    monthly_limit_usd: float = Field(ge=0.01, default=50.0)


class AlertRuleIn(BaseModel):
    threshold_percent: int = Field(ge=10, le=100, default=80)
    alert_type: str = Field(default="daily", pattern="^(daily|monthly)$")


class DailyReport(BaseModel):
    date: str
    total_users: int
    total_tokens: int
    total_cost_usd: float
    top_users: list[dict]


# ── Session 依赖 ──────────────────────────────────────────────────────

async def _get_session() -> AsyncSession:
    async with session_maker()() as s:
        yield s


# ── 业务逻辑 ──────────────────────────────────────────────────────────

async def _check_quota(db: AsyncSession, user_id: str) -> Quota | None:
    """检查并重置过期配额。"""
    quota = (await db.execute(
        select(Quota).where(Quota.user_id == user_id)
    )).scalar_one_or_none()

    if quota is None:
        return None

    now = datetime.now(timezone.utc)
    if quota.last_reset_date.date() < now.date():
        # 每日重置
        quota.daily_used_tokens = 0
        if quota.last_reset_date.month < now.month:
            # 每月重置
            quota.monthly_used_usd = 0.0
        quota.last_reset_date = now
        await db.commit()

    return quota


async def _check_alerts(db: AsyncSession, user_id: str, quota: Quota) -> None:
    """检查是否触发告警。"""
    from core.events.event_bus import Event, get_event_bus

    rules = (await db.execute(
        select(AlertRule).where(
            AlertRule.user_id == user_id,
            AlertRule.enabled == True,
        )
    )).scalars().all()

    for rule in rules:
        if rule.alert_type == "daily":
            used_percent = (quota.daily_used_tokens / max(quota.daily_limit_tokens, 1)) * 100
        else:
            used_percent = (quota.monthly_used_usd / max(quota.monthly_limit_usd, 0.01)) * 100

        if used_percent >= rule.threshold_percent:
            await get_event_bus().publish(
                Event(
                    topic="token.quota_alert",
                    payload={
                        "user_id": user_id,
                        "alert_type": rule.alert_type,
                        "used_percent": round(used_percent, 1),
                        "threshold": rule.threshold_percent,
                    },
                    sender=PLUGIN_NAME,
                )
            )


# ── API 端点 ────────────────────────────────────────────────────────────

router = APIRouter(tags=[PLUGIN_NAME])


@router.get("/health")
async def health() -> dict[str, Any]:
    return {"plugin": PLUGIN_NAME, "status": "ok"}


@router.post("/usage", status_code=201)
async def record_usage(
    payload: UsageRecordIn,
    db: AsyncSession = Depends(_get_session),
) -> dict:
    """记录一次 LLM 调用的 token 用量。"""
    usage = TokenUsage(
        user_id=payload.user_id,
        model=payload.model,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        total_cost_usd=payload.total_cost_usd,
        endpoint=payload.endpoint,
    )
    db.add(usage)

    # 更新配额
    quota = await _check_quota(db, payload.user_id)
    if quota is not None:
        total = payload.input_tokens + payload.output_tokens
        quota.daily_used_tokens += total
        quota.monthly_used_usd += payload.total_cost_usd
        await db.commit()

        # 检查告警
        await _check_alerts(db, payload.user_id, quota)
    else:
        await db.commit()

    return {"status": "recorded", "usage_id": usage.id}


@router.get("/usage/{user_id}", response_model=list)
async def get_user_usage(
    user_id: str,
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(_get_session),
):
    """查询用户的历史用量。"""
    stmt = (
        select(TokenUsage)
        .where(TokenUsage.user_id == user_id)
        .order_by(TokenUsage.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": r.id,
            "model": r.model,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "total_cost_usd": r.total_cost_usd,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/quota/{user_id}", response_model=UsageSummary)
async def get_quota(
    user_id: str,
    db: AsyncSession = Depends(_get_session),
):
    """查询用户配额状态。"""
    quota = await _check_quota(db, user_id)
    if quota is None:
        raise HTTPException(status_code=404, detail="用户未配置配额")

    return UsageSummary(
        user_id=user_id,
        daily_tokens_used=quota.daily_used_tokens,
        daily_limit=quota.daily_limit_tokens,
        daily_percent=round(
            quota.daily_used_tokens / max(quota.daily_limit_tokens, 1) * 100, 1
        ),
        monthly_usd_used=round(quota.monthly_used_usd, 4),
        monthly_limit=quota.monthly_limit_usd,
        monthly_percent=round(
            quota.monthly_used_usd / max(quota.monthly_limit_usd, 0.01) * 100, 1
        ),
        is_active=quota.is_active,
    )


@router.post("/quota/{user_id}", response_model=UsageSummary)
async def set_quota(
    user_id: str,
    payload: QuotaIn,
    db: AsyncSession = Depends(_get_session),
):
    """设置或更新用户配额。"""
    quota = (await db.execute(
        select(Quota).where(Quota.user_id == user_id)
    )).scalar_one_or_none()

    if quota is None:
        quota = Quota(user_id=user_id)
        db.add(quota)

    quota.daily_limit_tokens = payload.daily_limit_tokens
    quota.monthly_limit_usd = payload.monthly_limit_usd
    await db.commit()
    await db.refresh(quota)

    return UsageSummary(
        user_id=user_id,
        daily_tokens_used=quota.daily_used_tokens,
        daily_limit=quota.daily_limit_tokens,
        daily_percent=round(
            quota.daily_used_tokens / max(quota.daily_limit_tokens, 1) * 100, 1
        ),
        monthly_usd_used=round(quota.monthly_used_usd, 4),
        monthly_limit=quota.monthly_limit_usd,
        monthly_percent=round(
            quota.monthly_used_usd / max(quota.monthly_limit_usd, 0.01) * 100, 1
        ),
        is_active=quota.is_active,
    )


@router.get("/report/daily", response_model=DailyReport)
async def daily_report(
    date: str | None = None,
    db: AsyncSession = Depends(_get_session),
):
    """生成每日汇总报告。"""
    if date is None:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    start = datetime.fromisoformat(f"{date}T00:00:00+00:00")
    end = start + timedelta(days=1)

    stmt = select(TokenUsage).where(
        TokenUsage.created_at >= start,
        TokenUsage.created_at < end,
    )
    rows = (await db.execute(stmt)).scalars().all()

    # 按用户汇总
    user_totals: dict[str, dict] = {}
    for r in rows:
        if r.user_id not in user_totals:
            user_totals[r.user_id] = {"tokens": 0, "cost": 0.0}
        user_totals[r.user_id]["tokens"] += r.input_tokens + r.output_tokens
        user_totals[r.user_id]["cost"] += r.total_cost_usd

    total_tokens = sum(v["tokens"] for v in user_totals.values())
    total_cost = sum(v["cost"] for v in user_totals.values())

    top_users = sorted(
        [{"user_id": k, **v} for k, v in user_totals.items()],
        key=lambda x: x["tokens"],
        reverse=True,
    )[:10]

    return DailyReport(
        date=date,
        total_users=len(user_totals),
        total_tokens=total_tokens,
        total_cost_usd=round(total_cost, 4),
        top_users=top_users,
    )


@router.post("/alert-rules/{user_id}", status_code=201)
async def create_alert_rule(
    user_id: str,
    payload: AlertRuleIn,
    db: AsyncSession = Depends(_get_session),
):
    """创建告警规则。"""
    rule = AlertRule(
        user_id=user_id,
        threshold_percent=payload.threshold_percent,
        alert_type=payload.alert_type,
    )
    db.add(rule)
    await db.commit()
    return {"status": "created", "rule_id": rule.id}


# ── 注册入口 ────────────────────────────────────────────────────────────

async def _daily_reset_task():
    """定时任务：每日重置配额计数器。"""
    from core.events.event_bus import Event, get_event_bus

    logger.info("Running daily quota reset")
    async with session_maker()() as db:
        stmt = select(Quota).where(Quota.is_active == True)
        quotas = (await db.execute(stmt)).scalars().all()
        now = datetime.now(timezone.utc)
        reset_count = 0
        for q in quotas:
            if q.last_reset_date.date() < now.date():
                q.daily_used_tokens = 0
                if q.last_reset_date.month < now.month:
                    q.monthly_used_usd = 0.0
                q.last_reset_date = now
                reset_count += 1
        await db.commit()

    await get_event_bus().publish(
        Event(
            topic="token.daily_reset",
            payload={"reset_count": reset_count, "date": now.strftime("%Y-%m-%d")},
            sender=PLUGIN_NAME,
        )
    )
    logger.info("Daily reset complete: %d quotas reset", reset_count)


def register(app, config: dict[str, Any] | None = None) -> None:
    """平台挂载入口。"""
    import asyncio

    cfg = config or {}
    db_url = cfg.get(
        "database_url",
        os.environ.get(
            "TOKEN_MANAGER_DATABASE_URL",
            "postgresql+asyncpg://ddw:ddw@127.0.0.1:5432/token_manager",
        ),
    )

    asyncio.get_event_loop().run_until_complete(
        init_db(database_url=db_url)
    )

    app.include_router(router, prefix=PLUGIN_PREFIX, tags=[PLUGIN_NAME])
    logger.info("token-manager plugin registered (api=%s)", PLUGIN_PREFIX)
```

对应 `manifest.yaml`：

```yaml
name: token-manager
version: 0.1.0
description: "LLM 用量追踪与配额管理"
author: "DDW Team"
license: "MIT"
isolation: inline
engine: ">=2.0.0"
permissions:
  - "database:token_manager"
config:
  required:
    - database_url
  optional:
    daily_reset_hour: 0
    alert_default_threshold: 80
dependencies:
  plugins: {}
  python:
    - pydantic>=2.0
    - sqlalchemy>=2.0
    - asyncpg
events:
  produces:
    - "token.quota_alert"
    - "token.daily_reset"
  consumes:
    - "agent.request"
```

---

## 12. 最佳实践

### 12.1 错误处理

```python
# ✅ 正确：捕获异常，返回有意义的错误信息
@router.get("/items/{item_id}")
async def get_item(item_id: int, db: AsyncSession = Depends(_get_session)):
    try:
        item = await db.get(MyModel, item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
        return item
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get item %s", item_id)
        raise HTTPException(status_code=500, detail="内部服务器错误")

# ❌ 错误：吞掉异常，返回模糊信息
@router.get("/items/{item_id}")
async def get_item(item_id: int, db=Depends(_get_session)):
    try:
        return await db.get(MyModel, item_id)
    except:
        return None  # 客户端不知道发生了什么
```

### 12.2 日志规范

```python
import logging

logger = logging.getLogger(__name__)  # ✅ 使用模块级 logger

# ✅ 正确：结构化日志，包含上下文
logger.info("Plugin %s registered (api=%s)", PLUGIN_NAME, PLUGIN_PREFIX)
logger.warning("Config validation failed for %s: missing api_key", self.name)
logger.exception("Failed to load plugin %s: %s", name, exc)

# ❌ 错误：使用 print
print(f"Plugin registered: {PLUGIN_NAME}")  # 不要这样做
```

### 12.3 安全注意事项

- **永远不要**在代码或日志中硬编码 API Key、密码
- 使用 `self.get_config("api_key")` 或环境变量读取敏感信息
- 对所有用户输入进行验证（Pydantic 模型 + Field 约束）
- 数据库查询使用参数化查询（SQLAlchemy ORM 自动处理）
- 声明最小必要权限（`permissions` 字段）

### 12.4 性能优化

- 数据库连接池配置：`pool_size=5, max_overflow=10, pool_pre_ping=True`
- 使用 `expire_on_commit=False` 避免不必要的延迟加载
- 异步 I/O：所有数据库操作和 HTTP 调用使用 `async/await`
- 避免在请求处理中执行阻塞操作

### 12.5 代码风格

```bash
# 使用 ruff 格式化
ruff format .
ruff check --fix .
```

---

## 13. 常见问题

### 13.1 插件加载失败排查

```bash
# 查看插件状态
ddw plugin status my-plugin

# 查看详细信息
ddw plugin info my-plugin

# 检查日志
tail -f logs/ddw-core.log | grep "my-plugin"
```

常见原因：

1. `manifest.yaml` 缺少必填字段 → 检查 `name`, `version`, `description`
2. `__init__.py` 未暴露 `register()` 函数 → 确保函数签名正确
3. Python 依赖未安装 → `pip install -r requirements.txt`
4. 数据库连接失败 → 检查 `DATABASE_URL` 配置

### 13.2 权限问题

```
Error: plugin 'my-plugin' requires permission 'network' but not granted
```

在 `manifest.yaml` 中声明所需权限，并确保平台管理员已授权：

```yaml
permissions:
  - network
  - "database:my_plugin"
```

### 13.3 数据库迁移

插件使用 `create_all()` 自动建表。如需修改已有表结构：

1. 在 `on_enable()` 中添加 Alembic 迁移检查
2. 使用 Alembic 管理生产数据库迁移
3. 确保新字段有默认值，保持向后兼容

### 13.4 沙箱模式限制

沙箱模式下插件无法直接访问：

- 平台进程的内存空间
- 共享文件系统（除非声明 `storage` 权限）
- 其他插件的 API（需通过事件系统通信）

解决方案：

- 使用事件系统进行跨插件通信
- 通过 `config` 传递必要配置
- 声明所需的 `permissions`

---

## 14. 附录

### 14.1 manifest.yaml 字段速查表

| 字段 | 类型 | 必填 | 默认值 |
|------|------|------|--------|
| `name` | string | ✅ | — |
| `version` | string | ✅ | — |
| `description` | string | ✅ | — |
| `author` | string | ✅ | — |
| `license` | string | ✅ | — |
| `engine` | string | — | `>=0.1.0` |
| `isolation` | string | — | `inline` |
| `permissions` | list[str] | — | `[]` |
| `config.required` | list[str] | — | `[]` |
| `config.optional` | dict | — | `{}` |
| `dependencies.plugins` | dict | — | `{}` |
| `dependencies.python` | list[str] | — | `[]` |
| `events.produces` | list[str] | — | `[]` |
| `events.consumes` | list[str] | — | `[]` |
| `quality.ai_output` | object | — | — |
| `trial` | object | — | — |
| `ecosystem` | object | — | — |

### 14.2 PluginBase API 速查表

| 方法/属性 | 模式 | 说明 |
|-----------|------|------|
| `PluginBase.__init__(app, config, manifest)` | inline | 构造函数 |
| `PluginBase.setup()` | inline | 重写：声明路由、订阅事件 |
| `PluginBase.add_route(path, **kwargs)` | inline | 声明 GET 路由 |
| `PluginBase.get(path, **kwargs)` | inline | 声明 GET 路由 |
| `PluginBase.post(path, **kwargs)` | inline | 声明 POST 路由 |
| `PluginBase.register()` | inline | 挂载路由到宿主 app |
| `DDWPlugin.on_install()` | ABC | 安装回调 |
| `DDWPlugin.on_enable()` | ABC | 启用回调 |
| `DDWPlugin.on_disable()` | ABC | 禁用回调 |
| `DDWPlugin.on_uninstall()` | ABC | 卸载回调 |
| `DDWPlugin.get_config(key)` | ABC | 获取配置值 |
| `DDWPlugin.get_db_session()` | ABC | 获取数据库 Session |
| `DDWPlugin.publish_event(event)` | ABC | 发布事件 |
| `DDWPlugin.register_api(router)` | ABC | 注册额外 API 路由 |

### 14.3 错误码对照表

| 错误码 | 说明 | 常见原因 |
|--------|------|----------|
| 1001 | manifest.yaml 缺失 | 插件目录无 manifest.yaml |
| 1002 | 必填字段缺失 | name/version/description 未填 |
| 1003 | 版本格式错误 | 非标准 SemVer |
| 2001 | 依赖解析失败 | 插件依赖的其他插件未安装 |
| 2002 | 版本约束不满足 | 依赖版本不符合 constraint |
| 2003 | 循环依赖 | 插件 A → B → A |
| 3001 | Python 依赖缺失 | pip install 失败 |
| 3002 | import 失败 | 模块导入错误 |
| 3003 | register() 未定义 | `__init__.py` 缺少 `register` 函数 |
| 4001 | 数据库连接失败 | DATABASE_URL 配置错误 |
| 4002 | 表创建失败 | 数据库权限不足 |
| 5001 | 权限被拒绝 | 平台未授权所需权限 |
| 5002 | 沙箱启动失败 | 子进程创建异常 |
| 6001 | 配置验证失败 | required 配置项缺失 |
| 6002 | 配置 hash 冲突 | 配置热重载冲突 |

---

## 15. 适配器插件标准接口（2026-07-13 拍板）

> DDW 的核心架构模式是**插件组合式部署**：每个插件是最小可用单元，客户的业务场景落地 = 多个插件的组合装配。
> 本节定义所有适配器插件必须实现的标准接口，确保不同厂商的适配器可以被业务插件统一调用。

### 15.1 适配器插件的定位

```
客户的"AI 智能客服"部署 = 
  ddw-smart-cs（客服核心插件）
  + ddw-adapter-dingtalk（钉钉身份适配器）
  + ddw-adapter-feishu（飞书身份适配器）
  + ddw-adapter-wecom（企微身份适配器）
  + ddw-cs-knowledge（客服知识库插件）
  + ddw-ent-knowledge（企业知识库同步插件）
  + ddw-permission-engine（权限引擎，Casbin）
  + [按客户需要] ddw-adapter-yonyou-u8（用友适配器）
  + [按客户需要] ddw-adapter-kingdee（金蝶适配器）
```

### 15.2 AdapterBase 基类

所有适配器插件必须继承 `AdapterBase`，该类继承自 `PluginBase`：

```python
from abc import abstractmethod
from typing import List, Optional, Dict, Any
from sdk.plugin_base import PluginBase

class AdapterBase(PluginBase):
    """DDW 适配器插件基类。
    
    所有对接外部系统（钉钉/飞书/企微/ERP/MES/OA/CRM）的适配器
    必须继承此类并实现抽象方法。
    """
    
    @property
    @abstractmethod
    def adapter_type(self) -> str:
        """适配器类型标识，如 'identity' / 'erp' / 'oa' / 'crm' / 'mes'"""
        pass
    
    @property
    @abstractmethod
    def vendor_name(self) -> str:
        """厂商名称，如 'dingtalk' / 'kingdee' / 'yonyou'"""
        pass
    
    # === 身份同步接口（identity 类适配器必须实现） ===
    
    @abstractmethod
    def sync_users(self) -> List[Dict[str, Any]]:
        """同步用户列表。
        
        Returns:
            List[{
                'external_id': str,      # 厂商系统中的用户ID
                'name': str,             # 用户姓名
                'email': Optional[str],  # 邮箱
                'phone': Optional[str],  # 手机号
                'department': str,       # 部门名称
                'title': Optional[str],  # 职位
                'roles': List[str],      # 角色列表
                'status': str,           # 'active' / 'inactive'
                'channel': str,          # 来源渠道 ('dingtalk' / 'feishu' / 'wecom')
            }]
        """
        pass
    
    @abstractmethod
    def sync_departments(self) -> List[Dict[str, Any]]:
        """同步组织架构/部门列表。
        
        Returns:
            List[{
                'external_id': str,      # 厂商系统中的部门ID
                'name': str,             # 部门名称
                'parent_id': Optional[str],  # 上级部门ID
                'leader': Optional[str],     # 负责人用户ID
            }]
        """
        pass
    
    @abstractmethod
    def sync_roles(self) -> List[Dict[str, Any]]:
        """同步角色/权限组。
        
        Returns:
            List[{
                'external_id': str,      # 厂商系统中的角色ID
                'name': str,             # 角色名称
                'description': Optional[str],
                'permissions': List[str], # 权限标识列表
            }]
        """
        pass
    
    # === 权限判断接口（所有适配器必须实现） ===
    
    @abstractmethod
    def check_permission(
        self, 
        user_id: str, 
        resource: str, 
        action: str
    ) -> bool:
        """判断用户是否有权执行指定操作。
        
        Args:
            user_id: 用户ID（external_id 或内部ID）
            resource: 资源标识（如 'erp:order:read' / 'mes:production:query'）
            action: 操作类型（'read' / 'write' / 'admin'）
        
        Returns:
            True=允许, False=拒绝
        """
        pass
    
    # === 业务数据查询接口（erp/mes/crm/oa 类适配器实现） ===
    
    def query_business_data(
        self, 
        user_id: str, 
        query_type: str, 
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """查询业务数据（带权限控制）。
        
        默认实现：检查权限后返回数据或拒绝。
        子类可覆盖以实现具体的 API 调用逻辑。
        
        Args:
            user_id: 用户ID
            query_type: 查询类型（如 'order_list' / 'inventory' / 'customer_info'）
            params: 查询参数
        
        Returns:
            {
                'success': bool,
                'data': Optional[dict],
                'error': Optional[str],  # 拒绝时返回委婉拒绝话术
                'audit_log': dict,       # 审计日志信息
            }
        """
        # 默认：权限检查 + 委婉拒绝
        if not self.check_permission(user_id, f"{self.vendor_name}:{query_type}", "read"):
            return {
                'success': False,
                'data': None,
                'error': '该信息暂时无法为您查询，建议联系您的专属业务对接人。',
                'audit_log': {
                    'user_id': user_id,
                    'resource': f"{self.vendor_name}:{query_type}",
                    'action': 'read',
                    'result': 'denied',
                }
            }
        # 子类覆盖此方法以实现实际查询
        return {
            'success': True,
            'data': None,
            'error': None,
            'audit_log': {
                'user_id': user_id,
                'resource': f"{self.vendor_name}:{query_type}",
                'action': 'read',
                'result': 'allowed',
            }
        }
    
    # === 健康检查接口（所有适配器必须实现） ===
    
    @abstractmethod
    def health_check(self) -> Dict[str, Any]:
        """检查外部系统连接状态。
        
        Returns:
            {
                'status': 'healthy' / 'degraded' / 'unhealthy',
                'vendor': str,
                'last_sync': Optional[str],  # ISO 时间戳
                'error': Optional[str],
            }
        """
        pass
```

### 15.3 适配器插件 manifest.yaml 扩展字段

```yaml
# 在标准 manifest.yaml 基础上，适配器插件必须声明：
adapter:
  type: "identity"          # identity / erp / oa / crm / mes / bi
  vendor: "dingtalk"        # 厂商标识
  protocol: "oauth2.0"      # 认证协议
  api_base_url: "https://api.dingtalk.com"
  sync_interval: 3600       # 同步间隔（秒）
  required_permissions:     # 适配器自身需要的权限
    - "user:read"
    - "department:read"
```

### 15.4 适配器优先级矩阵

| 优先级 | 适配器 | 适用场景 |
|:------:|:-------|:---------|
| P0 | 钉钉/飞书/企微身份适配器 | V1 客服插件必备 |
| P1 | LDAP/AD、用友U8、金蝶、泛微OA | V1.5 权限底座完善 |
| P2 | SAP、致远OA、纷享销客、帆软、鼎捷、MES | V2 FDE 按客户做 |
| P3 | 管家婆、速达 | V3 暂不考虑 |

---

## 16. 已验证插件清单（2026-08-01）

> 来源：MiniMax Code CLI 在16G设备开发 +32G设备集成验收

### 16.1 验收通过的插件

| 插件 | 类型 | 测试 | manifest | SDK | 路由前缀 | 状态 |
|:-----|:-----|:-----|:---------|:---|:---------|:-----|
| ddw-adapter-registry | 轻量 | 6/6 | ✅ | ✅ | `/api/v1/plugins/ddw-adapter-registry` | ✅ 已进 Gitea |
| ddw-email-assistant | 完整 | 34/34 | ✅ | ✅ | `/api/v1/plugins/ddw-email-assistant` | ✅ 已进 Gitea |
| ddw-feedback-loop | 轻量 | 6/6 | ✅ | ✅ | `/api/v1/plugins/ddw-feedback-loop` | ✅ 已进 Gitea |
| ddw-knowledge-hierarchy | 轻量 | 6/6 | ✅ | ✅ | `/api/v1/plugins/ddw-knowledge-hierarchy` | ✅ 已进 Gitea |
| ddw-persona-engine | 轻量 | 6/6 | ✅ | ✅ | `/api/v1/plugins/ddw-persona-engine` | ✅ 已进 Gitea |
| ddw-smart-cs | 完整 | 18/18 | ✅ | ✅ | `/api/v1/plugins/ddw-smart-cs` | ✅ 已进 Gitea |
| ddw-sop-engine | 轻量 | 6/6 | ✅ | ✅ | `/api/v1/plugins/ddw-sop-engine` | ✅ 已进 Gitea |
| ddw-trace-panel | 轻量 | 6/6 | ✅ | ✅ | `/api/v1/plugins/ddw-trace-panel` | ✅ 已进 Gitea |

### 16.2 待恢复插件

| 插件 | 状态 |
|:-----|:-----|
| ddw-industrial-data-access | ❌ 本机未找到，需从16G备份恢复 |

### 16.3 质量验证方法

1. **py_compile**：全量编译检查所有 `.py` 文件
2. **pytest**：每个插件独立测试（in-memory SQLite）
3. **manifest 五必填**：name / version / description / author / license
4. **路由前缀**：必须为 `/api/v1/plugins/{plugin-name}`
5. **SDK 兼容性**：用32G正式 SDK（v2 merged）+ Python3.9 验证
6. **安全检查**：零硬编码 API Key、零 stub、LLM 走网关委托

### 16.4 修复记录

| 修复项 | 影响插件 | 说明 |
|:-------|:---------|:-----|
| manifest 补 author + license | 6个轻量插件 | `DDW AI Hub Team` + `Apache-2.0` |
| LICENSE 全文 | 6个轻量插件 | Apache-2.0（12,623B） |
| 路由前缀修正 | email-assistant, smart-cs | `/api/email` → `/api/v1/plugins/...` |
| health 端点 | email-assistant | 新增 `GET /health` |
| manifest 格式 | smart-cs | `config_schema` → `config.optional` |
| README 补写 | smart-cs | 新增完整 README |
| ruff --fix | 9/9 | 27个 import 排序修复 |

---

## 十六、前端设计规范

> 详细规范见 `docs/DDW_Frontend_Design_Standard.md`

### 16.1 设计锚点

DDW 前端统一使用 **Ant Design 企业 OA 风格**（泛微E9/E10 + 蓝凌MK + 帆软FineBI）。

### 16.2 核心规则

| 规则 | 要求 |
|------|------|
| 主色 | `#1890FF`（Ant Design 标准蓝） |
| 深色区域 | `#001529`（顶栏+侧边栏） |
| 圆角 | `≤ 2px` |
| 边框 | `1px solid #D9D9D9` |
| 阴影 | 禁止装饰性 box-shadow |
| 渐变 | 禁止 linear-gradient / radial-gradient |
| 图标 | SVG（stroke 风格），禁止 emoji |
| 字体 | 系统字体 + mono 用于数据 |

### 16.3 去 AI 化

所有前端页面必须通过 `html-deai-pipeline` skill 的自检清单：
- 无 emoji 图标
- 无渐变背景
- 无 box-shadow 装饰
- 无 AI-slop 高频词（赋能/助力/一站式/打造/闭环）
- 无虚构数据

### 16.4 嵌入模式

所有页面支持 iframe 嵌入泛微OA/蓝凌MK/钉钉工作台/飞书工作台：
```html
<iframe src="https://ddw-ai.com/chat?token=SSO_TOKEN&platform=weaver" 
        style="width:100%;height:100vh;border:none;"></iframe>
```

### 16.5 页面清单

| 页面 | 路由 | 说明 |
|------|------|------|
| 数据概览 | `#/dashboard` | 统计卡片 + 操作日志 + 服务状态 |
| 插件管理 | `#/plugins` | 卡片网格 + 分类筛选 |
| 系统集成 | `#/integrations` | 飞书/钉钉/企微/泛微OA 连接管理 |
| AI 助手 | `#/chat` | 三段式（插件选择/对话/产物面板） |
| 技能管理 | `#/skills` | 技能列表 + CRUD + 调用统计 |
| 数字员工 | `#/agents` | 岗位卡片 + 职责 + 产量 + 合格率 |
| 知识库 | `#/knowledge` | 8 类知识库 + 权限矩阵 |
| 用户管理 | `#/users` | RBAC 权限 + 白名单 |
| 模型配置 | `#/llm` | Provider 管理 + 降级策略 |
| 系统设置 | `#/settings` | 租户 + 安全 + 备份 |

---

## 相关文档

- [DDW AI Hub 架构文档](./DDW_Architecture.md)
- [DDW AI Hub 部署指南](./DDW_Deployment_Guide.md)
- [Plugin SDK 接口规范](../cloud-llm/ddw-ai-hub/sdk/plugin_base.py)
- [PluginManager 源码](../cloud-llm/ddw-ai-hub/core/plugin_manager/manager.py)
- [参考插件：oral-clinic](../cloud-llm/ddw-plugins/oral-clinic/)

---

> 📝 **文档版本**：v1.0 | **最后更新**：2026-07-12 | **维护者**：DDW AI Hub Team
