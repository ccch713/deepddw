# TASK_SPEC: Skill 池（不可删状态机 + 三级管理）

> 优先级：P0  
> 预计工时：2-3 天  
> 插件名：ddw_skill_pool  
> 状态：待确认

---

## 1. 概述

Skill 池是 DDW 数字员工能力的基础注册表。所有 skill 在此统一管理，数字员工/员工可以"下载"（启用）skill 到自己的能力列表中。

**核心规则：Skill 只允许 enabled ↔ disabled 状态切换，任何层级都不能删除。**

## 2. 数据模型

### 2.1 Skill 定义（SkillDefinition）

```python
class SkillDefinition(Base):
    __tablename__ = "skill_definitions"
    
    id: int = Column(Integer, primary_key=True)
    tenant_id: int = Column(Integer, nullable=True)           # null = 平台级（所有租户共享）
    name: str = Column(String(200), nullable=False)           # 如 ddw.llm.chat
    display_name: str = Column(String(100), nullable=False)   # 如 "通用对话"
    category: str = Column(String(50), default="chat")        # chat/tool/data/integ
    description: str = Column(Text, default="")
    triggers: list = Column(JSON, default=[])                  # 触发词列表
    yaml_config: str = Column(Text, default="")               # YAML 配置内容
    version: str = Column(String(20), default="1.0.0")
    status: str = Column(String(20), default="enabled")       # enabled / disabled
    is_system: bool = Column(Boolean, default=False)          # 系统内置 skill 不可停用
    download_count: int = Column(Integer, default=0)
    created_at: datetime = Column(DateTime, default=utcnow)
    updated_at: datetime = Column(DateTime, default=utcnow, onupdate=utcnow)
```

### 2.2 Skill 分配记录（SkillAssignment）

```python
class SkillAssignment(Base):
    __tablename__ = "skill_assignments"
    
    id: int = Column(Integer, primary_key=True)
    tenant_id: int = Column(Integer, nullable=False)
    skill_id: int = Column(Integer, ForeignKey("skill_definitions.id"), nullable=False)
    assignee_type: str = Column(String(20), nullable=False)   # "agent" / "employee"
    assignee_id: int = Column(Integer, nullable=False)        # agent_id 或 employee_id
    enabled: bool = Column(Boolean, default=True)             # 在该 assignee 下的启用/停用状态
    assigned_by: int = Column(Integer, nullable=True)
    assigned_at: datetime = Column(DateTime, default=utcnow)
    updated_at: datetime = Column(DateTime, default=utcnow, onupdate=utcnow)
```

## 3. 状态机

```
              公司管理员停用
    enabled ────────────────→ disabled
      ↑                         │
      │    公司管理员/部门管理员启用
      └─────────────────────────┘
      
    ⚠️ 任何层级均无"删除"操作
    ⚠️ 系统内置 skill（is_system=True）不可停用
```

## 4. API 端点

```yaml
# Skill 定义（公司/部门管理员）
GET    /api/v1/skills                          # 列表（含下载次数、状态）
GET    /api/v1/skills/{id}                     # 详情
POST   /api/v1/skills                          # 创建新 skill
PUT    /api/v1/skills/{id}                     # 修改（名称/描述/触发词/YAML）
PUT    /api/v1/skills/{id}/toggle              # 启用/停用切换
POST   /api/v1/skills/{id}/download            # 下载（分配给某 agent/employee）

# Skill 分配
GET    /api/v1/skills/assignments              # 查询分配（?assignee_type=agent&assignee_id=xxx）
POST   /api/v1/skills/assignments              # 新增分配
PUT    /api/v1/skills/assignments/{id}         # 启用/停用分配
DELETE /api/v1/skills/assignments/{id}         # 移除分配（不是删除 skill，是从 agent 身上移除）
```

## 5. 前端页面

### 5.1 Skill 池总览（saas-admin.html#/skills）

- 表格：skill 名称 / 类型 / 触发词 / 调用次数 / 状态 / 最后更新 / 操作
- 操作列：
  - 公司管理员：详情 / 启用停用 / 编辑
  - 部门管理员：详情 / 分配给本部门数字员工
  - 员工：详情 / 下载（分配给自己）
- 注意：**没有"删除"按钮**
- 搜索框：按名称/触发词搜索
- 分类筛选：全部/对话/工具/数据/集成

### 5.2 Skill 详情弹窗

- 基本信息：名称、描述、类型、触发词
- YAML 配置编辑器（monospace textarea）
- 调用统计：总次数、近 7 天趋势
- 操作：启用/停用（不可删除）

## 6. 权限矩阵

| 操作 | owner | dept admin | member |
|------|-------|-----------|--------|
| 查看 skill 列表 | ✅ | ✅ | ✅ |
| 创建新 skill | ✅ | ✅ | ❌ |
| 编辑 skill | ✅ | ✅ | ❌ |
| 启用/停用 | ✅ | ✅ | ❌ |
| 分配给数字员工 | ✅ | ✅（本部门） | ❌ |
| 下载给自己 | ❌ | ✅ | ✅ |
| 删除 | ❌ | ❌ | ❌ |

## 7. 验收标准

| # | 验证项 | 预期结果 |
|---|--------|----------|
| 1 | 创建 skill | 新 skill 出现在列表中，状态=enabled |
| 2 | 停用 skill | 状态变为 disabled，数字员工不可用 |
| 3 | 重新启用 | 状态恢复 enabled |
| 4 | 无删除按钮 | 前端确认没有"删除"操作 |
| 5 | 分配给数字员工 | agent 详情页可见该 skill |
| 6 | pytest | 全部测试通过 |

## 8. 依赖

- 无外部依赖
- 与 AI 组织插件（TASK_SPEC_AI_ORG）共享 agent_id / employee_id 引用
