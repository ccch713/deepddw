# 任务
帮我开发 DDW AI Hub 的 6 个新插件（SOP 编排引擎、层级知识检索、Trace 可观测面板、IM 适配器注册表、角色引擎、反馈闭环），将 StaffDeck（AGPL-3.0）的设计灵感迁移为 DDW（Apache 2.0）原生插件。全新实现，不复制 StaffDeck 任何源码。

# 背景
- DDW AI Hub 是企业级 AI 底座平台（Apache 2.0），采用插件组合式架构
- 当前状态：插件 SDK 已就绪（plugin_base.py 含 PluginState 五态状态机），LLM Gateway 已可用，Token Manager 已可用
- 本次任务来源：深度研究 StaffDeck 后提取可借鉴的设计思路（SOP 编排、知识图谱检索、执行 Trace、角色管理、人机反馈闭环）
- 每个插件对应一份完整 PRD 文档，包含 ORM 模型设计、API 端点定义、伪代码示例、测试计划
- 代码规范必须完全对齐 DDW 插件开发规范 v2.3

# 验收标准
- 6 个插件全部按 PRD 文档规格实现，零偏离
- 每个插件目录包含：manifest.yaml、__init__.py（register 函数）、router.py（含 /health 端点）、models.py（如涉及数据）、services.py、requirements.txt、README.md、tests/
- API 前缀统一为 `/api/v1/plugins/{插件名}/`
- manifest.yaml 使用 `config: { optional: { key: default } }` 格式，禁止 `config_schema`
- SQLAlchemy ORM 使用 `Mapped[type]` + `mapped_column()` 语法（2.0 规范），禁止旧式 `Column()`
- 所有 LLM 调用走 DDW Gateway，不自配 Provider，不存 API Key
- pytest 全部通过，ruff check 零错误
- 每个步骤边写边测：写完一个文件 → py_compile 验证 → ruff check 验证 → 通过才写下一个

# 技术约束
- Python 3.11+
- FastAPI + SQLAlchemy 2.0（Mapped + mapped_column 语法，禁止旧式 Column）
- 异步框架 asyncio，不做同步阻塞调用
- 每个插件继承 SDK 的 `sdk/plugin_base.py:PluginBase`，使用 `sdk/plugin_state.py:PluginState`
- 数据库用 PostgreSQL（生产）+ SQLite（测试，内存模式）
- 测试框架 pytest + pytest-asyncio + httpx（AsyncClient 替代 TestClient）
- 代码格式化 ruff，不做自定义风格
- 目录名用连字符 `ddw-xxx-yyy`，Python 包名用下划线 `ddw_xxx_yyy`
- 所有插件是独立 Git 仓库，不和 DDW 主仓混放

# 工作模式
请按以下顺序执行：

1. **先读完全部文档**：先读 `docs/DDW_StaffDeck_Inspiration_Roadmap.md`（路线图），再读 5 个 PRD 文档（每个 10-53KB），再读 SDK 源码（`sdk/plugin_base.py`、`sdk/plugin_state.py`），全部读完再动手
2. **输出架构设计**：把 6 个插件的模块划分、数据流、关键类、依赖关系整理成一段文字给我看，我确认后再写代码
3. **按依赖链依次开发**：
   - Step 0a: SDK 增强 — 在 `sdk/plugin_base.py` 增加 `InterventionHooks` 类
   - Step 0b: SDK 增强 — 在 `sdk/plugin_base.py` 增加 `ExecutionTrace` 上下文管理器
   - Step 1: `ddw-adapter-registry`（独立）
   - Step 2: `ddw-sop-engine`（依赖 SDK-1）
   - Step 3: `ddw-knowledge-hierarchy`（可并行于 Step 2）
   - Step 4: `ddw-trace-panel`（依赖 SDK-2）
   - Step 5: `ddw-persona-engine`（依赖 adapter + sop）
   - Step 6: `ddw-feedback-loop`（依赖 trace + persona）
4. **每个插件完成后立即验证**：
   - Gate 1: `python3 -m py_compile <file>`
   - Gate 2: `ruff check --select=E,W,F <file>`
   - Gate 3: `pytest tests/ -v`
   - Gate 4: `ruff check .`
5. **全部完成后**：告诉我怎么跑、怎么验证每个插件，输出总览清单

# 交付形式
- 6 个插件各自的完整项目目录（含所有 .py 文件、manifest.yaml、requirements.txt、README.md、tests/）
- 全部 .py 文件直接在对话里给我，不要只贴片段
- SDK 增强部分的 patch（diff 格式）
- 每个插件的 pytest 运行结果（测试数量 + 耗时）
- 所有文件以实际代码块呈现，不要用"此处省略"或"参考 PRD"替代
- 关键设计决策在代码注释里说明 WHY
