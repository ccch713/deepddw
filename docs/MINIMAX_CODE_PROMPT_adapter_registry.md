# 任务
帮我开发 DDW AI Hub 的新插件，将 StaffDeck 的设计灵感迁移为 DDW（Apache 2.0）原生插件。本次只做 **1 个插件：ddw-adapter-registry（IM 适配器注册表）**。如果你能高质量完成这一个并跑通全部质量门禁，我会继续给你下一个插件。全新实现，不复制 StaffDeck 任何源码。

# 背景
- DDW AI Hub 是企业级 AI 底座平台（Apache 2.0），采用插件组合式架构
- 插件 SDK 已就绪：`sdk/plugin_base.py`（PluginBase 基类 + PluginState 五态状态机）、`sdk/plugin_state.py`
- LLM Gateway 和 Token Manager 已可用
- 本插件是基础设施层插件——IM 适配器注册表，负责统一管理飞书/企微/钉钉等多渠道适配器，提供注册→发现→健康检查→消息路由能力
- 对应 PRD 文档：`docs/PRD_ddw-adapter-registry_v1.0.0.md`，约 9.8KB，已定义完整的 ORM 模型、API 端点、接口规范
- 所有代码必须对齐 DDW 插件开发规范 v2.3

# 验收标准
- manifest.yaml 使用 `config: { optional: { key: default } }` 格式，禁止 `config_schema`
- `__init__.py` 暴露 `register(app, config=None)` 函数
- `router.py` 必须包含 `/health` 端点，返回 `{plugin, status, version, endpoints}`
- `models.py` 使用 SQLAlchemy 2.0 `Mapped[type]` + `mapped_column()` 语法，禁止旧式 `Column()`
- API 前缀统一为 `/api/v1/plugins/ddw-adapter-registry/`
- 核心接口：`ChannelAdapter` 抽象基类（含 `send/receive/health_check`），`AdapterRegistry` 注册表类（含 `register/unregister/discover/route`）
- pytest 全部通过（至少 3 个测试用例：注册适配器、健康检查端点、重复注册拒绝）
- ruff check 零错误
- 目录结构完整：manifest.yaml + __init__.py + router.py + models.py + services.py + requirements.txt + README.md + tests/

# 技术约束
- Python 3.11+，FastAPI + SQLAlchemy 2.0
- 异步框架 asyncio，不做同步阻塞调用
- 继承 SDK 的 `sdk/plugin_base.py:PluginBase`，使用 `sdk/plugin_state.py:PluginState`
- 测试框架：pytest + pytest-asyncio + httpx.AsyncClient（不要用 sync TestClient，不要用 anyio）
- 代码格式化：ruff，不做自定义风格
- 数据库：SQLite 内存模式（测试），PostgreSQL（生产）
- 目录名用连字符 `ddw-adapter-registry`，Python 包名用下划线 `ddw_adapter_registry`
- 所有 LLM 调用走 DDW Gateway，不自配 Provider，不硬编码 API Key

# 工作模式
**这是一个短任务，请在单次会话内完成。按以下 AHE Loop 严格执行：**

## Round 1：阅读理解（必须先做完再动手）
1. 读 PRD 文档：`docs/PRD_ddw-adapter-registry_v1.0.0.md`
2. 读 SDK 源码：`sdk/plugin_base.py`、`sdk/plugin_state.py`
3. 输出一段 5-8 行的模块设计概要（有哪些类、哪些端点、数据流怎么走），然后等我确认

## Round 2：写核心模型（models.py + manifest.yaml）
1. 创建 `plugins/ddw_adapter_registry/` 目录
2. 写 `manifest.yaml`（按 PRD §8.1 的 YAML 模板）
3. 写 `models.py`（按 PRD 的 ORM 设计，Mapped[] 语法）
4. **立即验证**：
   ```
   python3 -m py_compile plugins/ddw_adapter_registry/models.py
   ```
   如果报错 → 修复 → 重新验证 → 通过才能继续

## Round 3：写路由和服务（router.py + services.py + __init__.py）
1. 写 `services.py`：实现 `ChannelAdapter` 抽象基类 + `AdapterRegistry` 注册表类
2. 写 `router.py`：实现 `/health` + PRD 定义的业务端点
3. 写 `__init__.py`：暴露 `register(app, config=None)`
4. **立即验证**：
   ```
   python3 -m py_compile plugins/ddw_adapter_registry/*.py
   ruff check --select=E,W,F plugins/ddw_adapter_registry/
   ```
   任一报错 → 修复 → 重新验证 → 全部通过才能继续

## Round 4：写测试 + 跑通（tests/）
1. 创建 `tests/` 目录，写 `conftest.py`（AsyncClient fixture）+ `test_*.py`（≥3 个用例）
2. **跑测试**：
   ```
   cd plugins/ddw_adapter_registry && python3 -m pytest tests/ -v
   ```
3. 如果有 FAILED → 读报错信息 → 修复代码或测试 → **重新跑** → 直到 ALL PASSED
4. **只有在 pytest 全部通过后才算 Round 4 完成**

## Round 5：最终检查 + 报告
1. 跑最终门禁：
   ```
   cd plugins/ddw_adapter_registry
   ruff check --select=E,W,F .
   python3 -m pytest tests/ -v --tb=short
   ```
2. 输出完成报告（格式见下方）

## ⚠️ 中断恢复规则
如果你在任何 Round 中被中断，回复我以下信息：
```
📍 中断点：Round X - {当前在做的事}
✅ 已通过：Round 1/2/3/4
📁 已创建文件：xxx.py, yyy.py
❌ 最后报错：[粘贴报错信息]
```
然后我会告诉你从哪个 Round 继续。

# 交付形式
- 所有 .py 文件在对话里完整展示（不要只贴片段、不要"此处省略"）
- 每个 Round 的验证命令 + 输出结果截图式展示（把终端输出原样贴出来）
- 最终输出一份完成报告：

```
✅ ddw-adapter-registry v1.0.0 开发完成

文件清单：
  manifest.yaml (X bytes)
  __init__.py (X bytes)
  router.py (X bytes, Y 个端点)
  models.py (X bytes, Z 个 ORM 模型)
  services.py (X bytes)
  requirements.txt (X bytes)
  README.md (X bytes)
  tests/conftest.py (X bytes)
  tests/test_adapter_registry.py (X bytes, N 个用例)

质量门禁：
  py_compile: ✅
  ruff check: ✅ 0 errors
  pytest: ✅ N/N passed (Xs)

自验证清单：
  grep 'config_schema' manifest.yaml → 0 命中 ✅
  grep 'Column(' models.py → 0 命中 ✅  
  grep 'Mapped\[' models.py → >0 命中 ✅
  grep '/api/v1/plugins/' router.py → >0 命中 ✅
  grep '/health' router.py → >0 命中 ✅
  grep 'def register' __init__.py → >0 命中 ✅

偏离 PRD 说明：无偏离
```
