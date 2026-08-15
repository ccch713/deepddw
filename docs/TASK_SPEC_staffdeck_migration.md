# MiMo Code 编码任务：DDW AI Hub StaffDeck 灵感迁移

> 本文件是 MiMo Code CLI 的自包含任务规格。严格按此文档执行，不得偏离。

---

## 零、铁律（最高优先级，逐条执行前必须自检）

1. **每写一个 `.py` 文件后，立即执行三步验证，通过才能写下一个文件**：
   ```
   python3 -m py_compile <文件路径>    # 语法错误立刻捕获
   ruff check --select=E,W,F <文件路径>  # 格式+未使用导入（≤0 errors）
   ```
2. **写测试 → pytest → 通过 → 下一个文件。不写完所有文件再统一测。**
3. **API 前缀必须是 `/api/v1/plugins/{插件名}/`，不允许自定义前缀。**
4. **manifest.yaml 必须用 `config: { optional: { key: default } }` 格式，禁止 `config_schema`。**
5. **SQLAlchemy ORM 必须用 `Mapped[type]` + `mapped_column()` 语法（2.0 规范），禁止旧式 `Column()`。**
6. **每个插件的 `__init__.py` 必须暴露 `register(app, config=None)` 函数。**
7. **每个插件必须暴露 `/health` 端点，返回 `{plugin, status, version, endpoints}`。**
8. **所有 LLM 调用必须走 DDW Gateway（`ddw-llm-gateway`），插件不自配 LLM Provider，不存 API Key。**
9. **每个插件是独立 Git 仓库，目录名必须用连字符（`ddw-xxx-yyy`）。**
10. **开发完成后运行 `ruff check` 全量检查 + `pytest tests/` 全部通过，输出测试数量和耗时。**

---

## 一、项目背景

DDW AI Hub 是一个企业级 AI 底座平台（Apache 2.0），采用插件组合式架构。本次任务是将 StaffDeck（OpenBMB, AGPL-3.0）的设计灵感迁移为 DDW 的全新原生插件。

**关键法律红线**：StaffDeck 是 AGPL-3.0，DDW 是 Apache 2.0。本次开发为"策略 B — 仅提取设计思路，全新实现"。不可复制 StaffDeck 任何源码。

---

## 二、PRD 文档清单（必须逐文件阅读）

所有 PRD 位于以下路径，开发每个插件前**必须先完整阅读其对应 PRD**：

| 优先级 | PRD 文件 | 路径 | 大小 |
|:------:|:---------|:-----|:----:|
| — | Master Roadmap | `docs/DDW_StaffDeck_Inspiration_Roadmap.md` | 8.7 KB |
| P0 | SOP 编排引擎 | `docs/PRD_ddw-sop-engine_v1.0.0.md` | 53 KB |
| P0 | 层级知识检索 | `docs/PRD_ddw-knowledge-hierarchy_v1.0.0.md` | 30 KB |
| P1 | Trace 可观测性 | `docs/PRD_ddw-trace-panel_v1.0.0.md` | 18 KB |
| P1 | IM 适配器注册表 | `docs/PRD_ddw-adapter-registry_v1.0.0.md` | 9.8 KB |
| P2 | 角色+反馈+干预 | `docs/PRD_ddw-persona-feedback-intervention_v1.0.0.md` | 13 KB |

**强制阅读顺序**：先读 Roadmap → 再读每个插件 PRD → 再开始编码。不读完不写代码。

---

## 三、开发顺序（严格按此依赖链执行）

```
Step 0: 基础设施准备（参照 Roadmap §三 Phase 1）
  ├── 0a. SDK-1: sdk/plugin_base.py 增加 InterventionHooks 类
  │         (参照 PRD_ddw-persona-feedback-intervention §Part C)
  └── 0b. SDK-2: sdk/plugin_base.py 增加 ExecutionTrace 上下文管理器
            (参照 PRD_ddw-trace-panel §二)

Step 1: ddw-adapter-registry（无 SDK 依赖，可独立开发）
  └── 参照 PRD_ddw-adapter-registry_v1.0.0.md

Step 2: ddw-sop-engine（依赖 SDK-1 InterventionHooks）
  └── 参照 PRD_ddw-sop-engine_v1.0.0.md

Step 3: ddw-knowledge-hierarchy（独立，可并行于 Step 2）
  └── 参照 PRD_ddw-knowledge-hierarchy_v1.0.0.md

Step 4: ddw-trace-panel（依赖 SDK-2 ExecutionTrace）
  └── 参照 PRD_ddw-trace-panel_v1.0.0.md

Step 5: ddw-persona-engine（依赖 adapter-registry + sop-engine）
  └── 参照 PRD_ddw-persona-feedback-intervention §Part A

Step 6: ddw-feedback-loop（依赖 trace-panel + persona-engine）
  └── 参照 PRD_ddw-persona-feedback-intervention §Part B
```

**并行机会**：Step 1+2+3 如有多 Agent 可并行。Step 4 在 Step 0b 完成后也可并行。

---

## 四、每个插件的标准交付物清单

每个插件目录下必须包含以下文件（按 DDW 开发指南 §2.2）：

```
ddw-{插件名}/
├── manifest.yaml          # 必须：按照各自 PRD §8.1 的 YAML 内容
├── __init__.py            # 必须：暴露 register(app, config=None)
├── router.py              # 必须：FastAPI APIRouter + /health 端点
├── models.py              # 必须（如涉及数据）：SQLAlchemy 2.0 ORM
├── services.py            # 可选：业务逻辑
├── requirements.txt       # 必须：独立依赖清单
├── README.md              # 必须：插件文档（含英文版 README.md）
└── tests/
    ├── __init__.py
    ├── conftest.py         # 必须：pytest fixtures + SQLite 内存数据库
    └── test_*.py           # 必须：参照各自 PRD §7 测试计划
```

---

## 五、质量标准（AHE Loop 4-gate）

每个文件写完后依次执行，任一 gate 不通过则修复后重来：

```
Gate 1: python3 -m py_compile <file>     # 硬门槛，语法错误立刻捕获
Gate 2: ruff check --select=E,W,F <file>  # 格式+未使用导入 ≤0 errors
Gate 3: pytest tests/ -v                  # 全部通过
Gate 4: ruff check .                      # 最终 clean check
```

---

## 六、关键规范速查（写任何代码前对照）

### 6.1 API 路由前缀
```python
# ✅ 正确
PLUGIN_NAME = "ddw-sop-engine"
router = APIRouter(prefix=f"/api/v1/plugins/{PLUGIN_NAME}", tags=[PLUGIN_NAME])

# ❌ 错误
router = APIRouter(prefix="/api/sop", tags=["sop"])
```

### 6.2 manifest.yaml config
```yaml
# ✅ 正确
config:
  optional:
    timeout: 30
    model: "default"

# ❌ 错误
config_schema:
  timeout:
    type: integer
    default: 30
```

### 6.3 SQLAlchemy ORM
```python
# ✅ 正确（SQLAlchemy 2.0）
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class MyModel(Base):
    __tablename__ = "my_table"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=...)
    name: Mapped[str] = mapped_column(String(256), index=True)

# ❌ 错误（旧式语法）
from sqlalchemy import Column, String
id = Column(String(36), primary_key=True)
```

### 6.4 register(app) + health
```python
# __init__.py
PLUGIN_NAME = "ddw-xxx"
PLUGIN_VERSION = "1.0.0"

def register(app, config=None):
    from .router import router
    app.include_router(
        router,
        prefix=f"/api/v1/plugins/{PLUGIN_NAME}",
        tags=[PLUGIN_NAME],
    )

# router.py
@router.get("/health")
async def health():
    return {
        "plugin": PLUGIN_NAME,
        "status": "ok",
        "version": PLUGIN_VERSION,
        "endpoints": ["/resource1", "/resource2"],
    }
```

### 6.5 LLM 调用
```python
# ✅ 正确：走网关
from sdk.llm_gateway import get_gateway
gateway = get_gateway()
response = await gateway.chat(messages=[...], model="mimo-v2.5-pro")

# ❌ 错误：直接调 API
import openai
client = openai.OpenAI(api_key="sk-xxx")  # 绝对禁止
```

### 6.6 测试 fixtures
```python
# tests/conftest.py
@pytest.fixture
def app():
    app = FastAPI()
    from ddw_xxx import register
    register(app, config={})
    return app

@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient
    return TestClient(app)
```

---

## 七、自验证清单（每个插件完成后执行）

```bash
# 1. 文件完整性
ls -la ddw-{插件名}/manifest.yaml ddw-{插件名}/__init__.py ddw-{插件名}/router.py

# 2. API 前缀检查
grep -c '/api/v1/plugins/' ddw-{插件名}/router.py  # 必须 > 0

# 3. manifest 格式检查
grep -c 'config_schema' ddw-{插件名}/manifest.yaml  # 必须 = 0
grep -c 'config:' ddw-{插件名}/manifest.yaml         # 必须 > 0

# 4. SQLAlchemy 语法检查
grep -c 'Column(' ddw-{插件名}/models.py 2>/dev/null  # 应该 = 0（旧式语法）
grep -c 'Mapped\[' ddw-{插件名}/models.py 2>/dev/null  # 应该 > 0（新式语法）

# 5. health 端点检查
grep -c '/health' ddw-{插件名}/router.py  # 必须 > 0

# 6. register 函数检查
grep -c 'def register' ddw-{插件名}/__init__.py  # 必须 > 0

# 7. 测试通过
cd ddw-{插件名} && python3 -m pytest tests/ -v

# 8. 全量 ruff
ruff check ddw-{插件名}/
```

---

## 八、完成报告格式

每个插件完成后，输出如下格式的报告：

```
✅ {插件名} v{版本号} 开发完成

文件清单：
  manifest.yaml (X bytes)
  __init__.py (X bytes)
  router.py (X bytes, Y 个端点)
  models.py (X bytes, Z 个 ORM 模型)
  services.py (X bytes)
  tests/test_*.py (X 个测试用例)

质量门禁：
  Gate 1 (py_compile): ✅ 全部通过
  Gate 2 (ruff check): ✅ 0 errors
  Gate 3 (pytest): ✅ X/Y passed ({duration}s)
  Gate 4 (ruff check .): ✅ clean

偏离 PRD 说明：
  （如有任何与 PRD 不一致的地方，必须在此列出并说明理由。如无偏离，写"无偏离"。）
```

---

## 九、执行指令

从 Step 0 开始，按 §三 开发顺序依次执行。

每个 Step 开始前，先打印：
```
━━━ Step X: {插件名} ━━━
正在阅读 PRD: docs/PRD_{插件名}_v1.0.0.md ...
```

然后完整阅读对应 PRD，再开始编码。

**禁止跳过任何 Step。禁止跳过任何质量门禁。禁止偏离 PRD 规范。**

---

*本 TASK_SPEC 基于 DDW 插件开发规范 v2.3 + 6 个 PRD 文档生成。所有路径相对于 DDW 项目根目录。*
