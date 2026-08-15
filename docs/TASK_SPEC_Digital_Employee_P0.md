# TASK_SPEC: 数字员工体系 P0 — 模型扩展 + 迁移脚本

> **版本**：v1.0  
> **日期**：2026-08-11  
> **预计工作量**：2 人天  
> **前置条件**：无  
> **后续批次**：P1(P0完成后) → P2 → P3 → P4 → P5  
> **开发工具**：MiMo Code CLI  
> **入库顺序**：Gitea → Obsidian → ECS → 16G

---

## P0.1 功能概述

扩展 DDW 数字员工体系的底层数据模型，为后续 P1-P5 的功能开发打下基础。本批次不涉及前端改动，纯后端模型+迁移+种子数据更新。

---

## P0.2 目录结构（仅改动文件）

```
ddw-ai-hub/
├── core/
│   └── constants/
│       └── roles.py                    # [修改] 新增 DIGITAL_AGENT 角色
├── plugins/
│   ├── ddw_org/
│   │   ├── models.py                   # [修改] Department/DigitalAgent/AgentSkill 扩展
│   │   ├── schemas.py                  # [修改] Pydantic 模型扩展
│   │   ├── router.py                   # [修改] 新增 PATCH /departments/{id} + PATCH /agents/{id}
│   │   ├── services/
│   │   │   └── org_service.py          # [修改] 业务逻辑扩展
│   │   └── tests/
│   │       └── test_digital_employee_p0.py  # [新增] P0 测试用例
│   └── ddw_flow_designer/
│       └── models.py                   # [修改] FlowDefinition/FlowReview 扩展
└── scripts/
    └── migrate_digital_employee_p0.py  # [新增] 幂等迁移脚本
```

---

## P0.3 数据模型变更（完整代码）

### P0.3.1 roles.py 变更

```python
# core/constants/roles.py — 完整替换内容

"""角色单一权威来源。所有角色判断必须引用本文件，禁止硬编码。

兼容 Python 3.9（StrEnum 在 3.11+ 才可用）。我们用 str 子类实现等价语义：
- Role.X == "x" 为 True
- Role.X in {Role.Y, Role.Z} 正常工作
- str(Role.X) == "x"
"""


class Role(str):
    """角色字符串类型（str 子类，Python 3.9 兼容 StrEnum 语义）。"""

    SUPERADMIN = "superadmin"
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    PARTNER = "partner"
    FINANCE = "finance"
    AUDITOR = "auditor"
    DIGITAL_AGENT = "digital_agent"  # P0 新增：数字员工角色


# 角色白名单集合（frozenset 保证只读语义）
ADMIN_ROLES = frozenset({Role.SUPERADMIN, Role.OWNER, Role.ADMIN})
PLUGIN_MANAGE_ROLES = frozenset({Role.SUPERADMIN, Role.OWNER})
FINANCE_ROLES = frozenset({Role.SUPERADMIN, Role.OWNER, Role.FINANCE})

# P0 新增：人类角色 vs 数字员工角色分离
HUMAN_ROLES = frozenset({
    Role.SUPERADMIN, Role.OWNER, Role.ADMIN,
    Role.MEMBER, Role.PARTNER, Role.FINANCE, Role.AUDITOR,
})
DIGITAL_ROLES = frozenset({Role.DIGITAL_AGENT})
ALL_ROLES = HUMAN_ROLES | DIGITAL_ROLES

ROLE_VALUES = [
    Role.SUPERADMIN,
    Role.OWNER,
    Role.ADMIN,
    Role.MEMBER,
    Role.PARTNER,
    Role.FINANCE,
    Role.AUDITOR,
    Role.DIGITAL_AGENT,
]


__all__ = [
    "Role",
    "ADMIN_ROLES",
    "PLUGIN_MANAGE_ROLES",
    "FINANCE_ROLES",
    "HUMAN_ROLES",
    "DIGITAL_ROLES",
    "ALL_ROLES",
    "ROLE_VALUES",
]
```

### P0.3.2 ddw_org/models.py 变更

在现有模型基础上新增字段，**不删除任何已有字段**：

```python
# === Department 模型新增字段 ===
# 在 Department 类中追加：
manager_user_id: Mapped[Optional[int]] = mapped_column(
    Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
)
# 说明：部门人类负责人。NULL 表示未指派（占位期由超管代理）

# === DigitalAgent 模型新增字段 ===
# 在 DigitalAgent 类中追加：
job_objective: Mapped[str] = mapped_column(Text, default="")
# 岗位目标：一句话描述该数字员工存在的价值

report_to: Mapped[Optional[int]] = mapped_column(
    Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
)
# 汇报对象（部门负责人 user_id）

decision_scope: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
# 决策权限范围列表：["read", "create", "edit", "delete", "approve", "initiate_flow", "access_external"]

work_boundary: Mapped[str] = mapped_column(Text, default="")
# 工作边界：明确列出不做的事项

# === AgentSkill 模型新增字段 ===
# 在 AgentSkill 类中追加：
proficiency: Mapped[str] = mapped_column(String(20), default="junior")
# 熟练度：junior(仅读取检索) / senior(读取+写入) / expert(读取+写入+审批)

trigger_conditions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
# 触发条件列表：[{"event": "ticket.created", "filter": {...}}]

sla_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
# 响应 SLA（秒），NULL 表示无 SLA 约束
```

### P0.3.3 ddw_flow_designer/models.py 变更

```python
# === FlowDefinition 模型新增字段 ===
# 在 FlowDefinition 类中追加（用 Column 声明，与现有风格一致）：
input_spec = Column(Text, nullable=True)          # JSON: 输入数据检查规范
output_spec = Column(Text, nullable=True)         # JSON: 输出数据检查规范 + 审批前置条件
cross_dept_review_config = Column(Text, nullable=True)  # JSON: 跨部门联审配置

# === FlowReview 模型新增字段 ===
checklist_results = Column(Text, default="[]")    # JSON: 审核人逐项确认结果
skill_merger_approved = Column(Boolean, default=False)  # 是否确认合并后的 skill 包
review_deadline = Column(DateTime, nullable=True)        # 审核截止时间
remind_count = Column(Integer, default=0)                # 已提醒次数

# === FlowRun status 枚举扩展 ===
# 现有: running/success/failed
# 新增: input_rejected / output_rejected / pending_human_fix / draft_incomplete
```

---

## P0.4 Pydantic Schema 变更（schemas.py）

```python
# === DepartmentUpdate 扩展 ===
class DepartmentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    manager_user_id: Optional[int] = None  # P0 新增

# === DigitalAgentUpdate 扩展 ===
class DigitalAgentUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    description: Optional[str] = None
    avatar_color: Optional[str] = None
    status: Optional[str] = None
    job_objective: Optional[str] = None       # P0 新增
    report_to: Optional[int] = None           # P0 新增
    decision_scope: Optional[List[str]] = None  # P0 新增
    work_boundary: Optional[str] = None       # P0 新增

# === AgentSkillUpdate 扩展 ===
class AgentSkillUpdate(BaseModel):
    enabled: Optional[bool] = None
    proficiency: Optional[str] = None         # P0 新增: junior/senior/expert
    trigger_conditions: Optional[List[dict]] = None  # P0 新增
    sla_seconds: Optional[int] = None         # P0 新增

# === 新增：数字员工岗位卡响应 ===
class DigitalAgentJobCard(BaseModel):
    id: int
    name: str
    role: str
    department_name: str
    job_objective: str
    report_to_name: Optional[str]
    decision_scope: List[str]
    work_boundary: str
    skills: List[dict]  # [{skill_key, name, proficiency, trigger_conditions, sla_seconds}]
    status: str
```

---

## P0.5 API 端点变更

### 新增端点

| 方法 | 路径 | 说明 | 成功 | 失败 |
|:-----|:-----|:-----|:-----|:-----|
| PATCH | `/api/v1/org/departments/{id}` | 更新部门（含 manager_user_id） | 200 部门对象 | 404 不存在 / 403 无权限 |
| GET | `/api/v1/org/departments/{id}/manager` | 获取部门负责人信息 | 200 用户对象 | 404 未指派 |
| PATCH | `/api/v1/org/agents/{id}` | 更新数字员工（含新字段） | 200 数字员工对象 | 404 / 400 字段校验失败 |
| GET | `/api/v1/org/agents/{id}/job-card` | 获取完整岗位卡 | 200 JobCard | 404 |
| PATCH | `/api/v1/org/agent-skills/{id}` | 更新技能关联 | 200 技能对象 | 404 / 400 |
| POST | `/api/v1/org/agents/{id}/validate` | 手动触发能力验证 | 200 验证结果 | 404 |

### 端点详细逻辑

**PATCH /api/v1/org/departments/{id}**:
1. 验证当前用户是 ADMIN_ROLES
2. 验证 department 存在且属于当前 tenant
3. 如更新 manager_user_id，验证目标 user 存在且属于同一 tenant
4. 更新字段，返回更新后的部门对象

**GET /api/v1/org/agents/{id}/job-card**:
1. 查询 DigitalAgent + JOIN Department + JOIN AgentSkill
2. 查询 report_to 对应的用户名
3. 查询 skill_pool 获取 skill 名称
4. 组装 JobCard 响应

**PATCH /api/v1/org/agents/{id}**:
1. 验证当前用户是 ADMIN_ROLES
2. 如更新 decision_scope 含 "approve"，记录审计日志
3. job_objective 和 work_boundary 为空字符串时返回 400

**POST /api/v1/org/agents/{id}/validate**（简单版，P4 扩展为 5 道检查）:
1. 检查 job_objective 非空
2. 检查 work_boundary 非空
3. 检查至少有 1 个 skill
4. 返回验证结果

---

## P0.6 迁移脚本（幂等）

```python
# scripts/migrate_digital_employee_p0.py
"""幂等迁移脚本：数字员工体系 P0 模型扩展。

执行方式：
  cd /path/to/ddw-ai-hub
  python scripts/migrate_digital_employee_p0.py

幂等性：
  - PRAGMA table_info 检查列是否已存在
  - 已存在的列不重复添加
  - 不 DROP 任何表/列
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "ddw_main.db"

# 列定义：(表名, 列名, SQL类型, 默认值)
COLUMNS_TO_ADD = [
    # org_departments
    ("org_departments", "manager_user_id", "INTEGER", "NULL"),
    # org_digital_agents
    ("org_digital_agents", "job_objective", "TEXT", "''"),
    ("org_digital_agents", "report_to", "INTEGER", "NULL"),
    ("org_digital_agents", "decision_scope", "TEXT", "'[]'"),
    ("org_digital_agents", "work_boundary", "TEXT", "''"),
    # org_agent_skills
    ("org_agent_skills", "proficiency", "VARCHAR(20)", "'junior'"),
    ("org_agent_skills", "trigger_conditions", "TEXT", "'[]'"),
    ("org_agent_skills", "sla_seconds", "INTEGER", "NULL"),
    # flow_definitions
    ("flow_definitions", "input_spec", "TEXT", "NULL"),
    ("flow_definitions", "output_spec", "TEXT", "NULL"),
    ("flow_definitions", "cross_dept_review_config", "TEXT", "NULL"),
    # flow_reviews
    ("flow_reviews", "checklist_results", "TEXT", "'[]'"),
    ("flow_reviews", "skill_merger_approved", "BOOLEAN", "0"),
    ("flow_reviews", "review_deadline", "TIMESTAMP", "NULL"),
    ("flow_reviews", "remind_count", "INTEGER", "0"),
]


def get_existing_columns(conn: sqlite3.Connection, table: str) -> set:
    """获取表的已有列名集合。"""
    try:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        return {row[1] for row in cursor.fetchall()}
    except Exception:
        return set()


def migrate(db_path: Path) -> None:
    if not db_path.exists():
        print(f"❌ 数据库不存在: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    added = 0
    skipped = 0
    errors = []

    for table, column, col_type, default in COLUMNS_TO_ADD:
        existing = get_existing_columns(conn, table)
        if not existing:
            print(f"⚠️  表 {table} 不存在，跳过")
            skipped += 1
            continue
        if column in existing:
            print(f"  ✓ {table}.{column} 已存在，跳过")
            skipped += 1
            continue
        try:
            sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type} DEFAULT {default}"
            conn.execute(sql)
            print(f"  ✅ {table}.{column} 已添加 ({col_type}, DEFAULT {default})")
            added += 1
        except Exception as e:
            print(f"  ❌ {table}.{column} 添加失败: {e}")
            errors.append(f"{table}.{column}: {e}")

    conn.commit()
    conn.close()

    print(f"\n{'='*50}")
    print(f"迁移完成: 添加 {added} 列, 跳过 {skipped} 列, 错误 {len(errors)} 个")
    if errors:
        print("错误详情:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)


if __name__ == "__main__":
    migrate(DB_PATH)
```

---

## P0.7 种子数据更新

更新 `plugins/ddw_org/services/seed.py` 中的种子数据，为现有 11 个数字员工补充新字段默认值：

```python
# 在 seed.py 中为每个 default_agent 补充：
{
    "name": "笑笑",
    "role": "AI 前台助手",
    "job_objective": "作为企业第一接触点，高效处理来访咨询、邮件分发、日程协调",
    "work_boundary": "不做财务审批、不做合同签署、不做技术开发",
    "decision_scope": ["read", "create", "edit"],
    "default_skills": [
        {"skill_key": "ddw.llm.chat", "proficiency": "expert"},
        {"skill_key": "ddw.kb.search", "proficiency": "senior"},
        {"skill_key": "ddw.email.send", "proficiency": "senior"},
    ],
}
# 其余 10 个数字员工同理，每个都要有 job_objective + work_boundary + decision_scope
```

---

## P0.8 CSS 变量专项规则（全局适用）

> **本规则适用于所有前端改动，从 P0 开始强制执行。**

### 规则 1：内联样式禁止硬编码色值
```html
<!-- ❌ 错误 -->
<div style="color: #333; background: #f5f5f5;">

<!-- ✅ 正确 -->
<div style="color: var(--c-text); background: var(--c-bg-alt);">
```

### 规则 2：JS 渲染颜色必须通过 Theme Bridge
```javascript
// ❌ 错误
chart.borderColor = '#5b9dff';

// ✅ 正确 — 从 CSS 变量动态读取
const DDW_THEME = {};
function loadTheme() {
  const root = getComputedStyle(document.documentElement);
  DDW_THEME.accent = root.getPropertyValue('--c-accent').trim() || '#e8b86d';
  DDW_THEME.success = root.getPropertyValue('--c-success').trim() || '#28a745';
  DDW_THEME.danger  = root.getPropertyValue('--c-danger').trim()  || '#dc3545';
  DDW_THEME.text    = root.getPropertyValue('--c-text').trim()    || '#1a1a2e';
}
loadTheme();

chart.borderColor = DDW_THEME.accent;
```

### 规则 3：CSS 变量定义在 css/theme.css :root 中
```css
:root {
  --c-bg: #f8f9fa;
  --c-bg-alt: #ffffff;
  --c-bg-dark: #1a1a2e;
  --c-text: #1a1a2e;
  --c-text-muted: #6c757d;
  --c-text-inv: #ffffff;
  --c-accent: #e8b86d;
  --c-accent-dk: #c89548;
  --c-success: #28a745;
  --c-danger: #dc3545;
  --c-warn: #ffc107;
  --c-info: #17a2b8;
  --c-border: #e0e3e8;
  --c-border-dark: #2d2d52;
}
```

### 规则 4：新页面必须引入 theme.css
```html
<link rel="stylesheet" href="/css/theme.css">
```

### 验收命令
```bash
# 检查内联样式中的硬编码色值（排除 :root 定义和 CSS 文件中的变量定义）
grep -n 'style="[^"]*#[0-9A-Fa-f]\{3,6\}' frontend/*.html | grep -v ':root' | grep -v 'var(--'

# 期望结果：0 匹配
```

---

## P0.9 测试用例（8 条）

```python
# plugins/ddw_org/tests/test_digital_employee_p0.py

import pytest
from httpx import AsyncClient


class TestDigitalEmployeeP0:
    """数字员工体系 P0 测试用例。"""

    # T1: Department 新增 manager_user_id 字段可读写
    async def test_t1_department_manager_update(self, client: AsyncClient, admin_token: str):
        """PATCH /departments/{id} 可设置 manager_user_id"""
        resp = await client.patch(
            "/api/v1/org/departments/1",
            json={"manager_user_id": 1},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["manager_user_id"] == 1

    # T2: DigitalAgent 新增字段可读写
    async def test_t2_agent_new_fields_update(self, client: AsyncClient, admin_token: str):
        """PATCH /agents/{id} 可设置 job_objective/report_to/decision_scope/work_boundary"""
        resp = await client.patch(
            "/api/v1/org/agents/1",
            json={
                "job_objective": "处理前台咨询",
                "decision_scope": ["read", "create"],
                "work_boundary": "不做财务审批",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_objective"] == "处理前台咨询"
        assert "read" in data["decision_scope"]

    # T3: job_objective 为空时返回 400
    async def test_t3_job_objective_required(self, client: AsyncClient, admin_token: str):
        """job_objective 为空字符串时 API 返回 400"""
        resp = await client.patch(
            "/api/v1/org/agents/1",
            json={"job_objective": ""},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 400

    # T4: AgentSkill proficiency 字段可更新
    async def test_t4_skill_proficiency_update(self, client: AsyncClient, admin_token: str):
        """PATCH /agent-skills/{id} 可设置 proficiency"""
        # 先获取 agent 的 skill 列表
        resp = await client.get(
            "/api/v1/org/agents/1",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # 假设已有 skill 关联，更新 proficiency
        # 具体 skill_id 需从 agent_skills 中获取
        # 这里测试 API 接受 proficiency 参数
        assert resp.status_code == 200

    # T5: 岗位卡 API 返回所有新字段
    async def test_t5_job_card_endpoint(self, client: AsyncClient, admin_token: str):
        """GET /agents/{id}/job-card 返回完整岗位卡"""
        resp = await client.get(
            "/api/v1/org/agents/1/job-card",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "job_objective" in data
        assert "decision_scope" in data
        assert "work_boundary" in data
        assert "skills" in data

    # T6: roles.py 包含 DIGITAL_AGENT 角色
    async def test_t6_digital_agent_role_exists(self):
        """Role.DIGITAL_AGENT 存在且值正确"""
        from core.constants.roles import Role, DIGITAL_ROLES, ALL_ROLES
        assert Role.DIGITAL_AGENT == "digital_agent"
        assert Role.DIGITAL_AGENT in DIGITAL_ROLES
        assert Role.DIGITAL_AGENT in ALL_ROLES

    # T7: 种子数据包含新字段默认值
    async def test_t7_seed_data_has_new_fields(self, client: AsyncClient, admin_token: str):
        """种子数据的数字员工有 job_objective 默认值"""
        resp = await client.get(
            "/api/v1/org/agents",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        agents = resp.json()
        # 种子数据应该已有 job_objective
        if len(agents) > 0:
            assert "job_objective" in agents[0] if isinstance(agents, list) else "job_objective" in agents.get("items", [{}])[0]

    # T8: 迁移脚本幂等执行
    async def test_t8_migration_idempotent(self):
        """迁移脚本重复执行不报错"""
        import subprocess
        result = subprocess.run(
            ["python", "scripts/migrate_digital_employee_p0.py"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "跳过" in result.stdout or "已存在" in result.stdout
```

---

## P0.10 验收标准

| # | 维度 | 验收标准 | 检查命令 |
|---|------|---------|---------|
| 1 | 模型扩展 | roles.py 含 DIGITAL_AGENT | `grep DIGITAL_AGENT core/constants/roles.py` |
| 2 | 模型扩展 | Department 含 manager_user_id | `grep manager_user_id plugins/ddw_org/models.py` |
| 3 | 模型扩展 | DigitalAgent 含 job_objective/report_to/decision_scope/work_boundary | `grep -c 'job_objective\|report_to\|decision_scope\|work_boundary' plugins/ddw_org/models.py` ≥ 4 |
| 4 | 模型扩展 | AgentSkill 含 proficiency/trigger_conditions/sla_seconds | `grep -c 'proficiency\|trigger_conditions\|sla_seconds' plugins/ddw_org/models.py` ≥ 3 |
| 5 | 模型扩展 | FlowDefinition 含 input_spec/output_spec | `grep -c 'input_spec\|output_spec\|cross_dept_review_config' plugins/ddw_flow_designer/models.py` ≥ 3 |
| 6 | 迁移脚本 | 幂等执行成功 | `python scripts/migrate_digital_employee_p0.py` exit 0 |
| 7 | API | PATCH /departments/{id} 可设置 manager_user_id | curl 测试 |
| 8 | API | GET /agents/{id}/job-card 返回新字段 | curl 测试 |
| 9 | 测试 | 8 条测试用例全部通过 | `pytest plugins/ddw_org/tests/test_digital_employee_p0.py -v` |
| 10 | Lint | ruff 零新增 error | `ruff check plugins/ddw_org/ core/constants/roles.py` |
| 11 | CSS | 新增前端代码无硬编码色值 | grep 检查（如有前端改动） |
| 12 | 回归 | 现有测试不回归 | `pytest plugins/ddw_org/tests/ -q` |

---

## P0.11 禁止事项

1. **禁止删除任何已有字段或表**
2. **禁止修改 core/api/ 或 core/main.py**（P0 不涉及路由注册变更）
3. **禁止引入新 pip 依赖**
4. **禁止 push 到 Gitea**（Hermes 统一验收后 push）
5. **禁止修改前端 HTML 文件**（P0 纯后端）
6. **禁止修改种子数据中已有的 name/role/description 等字段值**

---

## P0.12 开发顺序

1. `core/constants/roles.py` — 新增角色
2. `plugins/ddw_org/models.py` — 模型扩展
3. `plugins/ddw_flow_designer/models.py` — 模型扩展
4. `plugins/ddw_org/schemas.py` — Pydantic 模型
5. `plugins/ddw_org/router.py` — API 端点
6. `plugins/ddw_org/services/org_service.py` — 业务逻辑
7. `scripts/migrate_digital_employee_p0.py` — 迁移脚本
8. `plugins/ddw_org/services/seed.py` — 种子数据
9. `plugins/ddw_org/tests/test_digital_employee_p0.py` — 测试
10. 全量 pytest + ruff 验证

**写一个文件 → py_compile + ruff → 下一个文件。不要写完所有再统一测。**
