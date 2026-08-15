# 基于 Reasonix 架构的 DDW 优化任务

## 背景

DeepSeek-Reasonix (github.com/esengine/DeepSeek-Reasonix) 是一个 26K+ stars 的 DeepSeek 原生编码代理，
其架构设计对 DDW AI Hub 有三个可落地的优化方向。

## 优化 1: LLM Gateway — Session-Affinity 路由

**文件**: `plugins/ddw-llm-gateway/load_balancer.py`

**现状**: LoadBalancer 每次请求独立选择 channel（优先级+加权随机+成功率过滤）。

**优化目标**: 添加 session-affinity 能力，同一用户的连续请求优先路由到同一 channel，
利用 DeepSeek prefix cache 降低 token 消耗。

**实现要点**:
1. 在 `LoadBalancer` 类中添加 `_session_affinity: dict[str, int]`（session_id → channel_id 映射）
2. 添加 `select_with_affinity(candidates, model, session_id=None)` 方法
3. 当 session_id 有对应 channel 且该 channel 仍在候选列表中且成功率 > 阈值时，优先返回
4. 添加 `clear_affinity(session_id)` 方法用于会话结束时清理
5. 保持原有 `select()` 方法不变（向后兼容）

## 优化 2: Plugin Manager — 启动超时降级

**文件**: `local-llm/ddw-ai-hub/core/plugin_manager/manager.py`

**现状**: 插件发现后直接加载，无启动超时控制。

**优化目标**: 参考 Reasonix 的 eager/background 分层启动模式，
添加启动超时降级机制——慢插件不阻塞平台启动。

**实现要点**:
1. 在 `PluginManifest` 中添加 `startup_tier: str = "eager"` 字段（eager/background/on_demand）
2. 在 `PluginManager` 中添加 `discover_with_tiers()` 方法，返回 `(eager_plugins, background_plugins)`
3. 添加 `LOAD_TIMEOUT_SECONDS = 10` 常量
4. eager 插件在主进程加载，超时的降级为 background
5. background 插件在后台线程延迟加载

## 优化 3: Plugin SDK — ReadOnlyHint + MCP 兼容注解

**文件**: `local-llm/ddw-ai-hub/sdk/plugin_base.py`

**现状**: PluginBase 无工具只读/读写分类。

**优化目标**: 参考 Reasonix 的 readOnlyHint 模式，让插件声明工具的读写属性，
支持并行执行优化。

**实现要点**:
1. 在 `PluginBase` 中添加 `def tool_annotations(self) -> dict[str, dict]:` 方法
2. 默认返回 `{}`（所有工具视为读写）
3. 子类可覆盖声明 `{"tool_name": {"readOnly": True}}`
4. 在 `plugin_state.py` 的 `PluginState` 中添加 `tool_annotations` 属性

## 约束

- 保持向后兼容，不破坏现有 API
- 所有新增代码必须有 docstring
- 遵循项目现有代码风格（Python type hints, dataclass）
- 修改后运行 `python -m py_compile` 验证语法
