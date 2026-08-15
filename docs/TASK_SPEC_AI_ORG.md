# TASK_SPEC: AI 组织（11 虚拟部门 + 数字员工 + 员工管理）

> 优先级：P0  
> 预计工时：3-5 天  
> 插件名：ddw_org  
> 状态：待确认

---

## 1. 概述

AI 组织是 DDW 的核心频道，管理企业虚拟部门架构。包含 3 个子模块：
- **部门管理**：预设 11 个虚拟部门，公司级管理员可改名称/介绍
- **数字员工**：每个部门预设 1 个数字员工，部门级管理员可配名称/技能
- **员工管理**：企业真实员工清单，可手动添加/导入，可从泛微同步

## 2. 数据模型

### 2.1 部门（Department）

```python
class Department(Base):
    __tablename__ = "org_departments"
    
    id: int = Column(Integer, primary_key=True)
    tenant_id: int = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    name: str = Column(String(100), nullable=False)          # 部门名称（可改）
    description: str = Column(Text, default="")               # 部门介绍（可改）
    sort_order: int = Column(Integer, default=0)              # 排序
    preset_id: str = Column(String(50), nullable=True)        # 预设标识（如 "dept_01"）
    created_at: datetime = Column(DateTime, default=utcnow)
    updated_at: datetime = Column(DateTime, default=utcnow, onupdate=utcnow)
```

### 2.2 数字员工（DigitalAgent）

```python
class DigitalAgent(Base):
    __tablename__ = "org_digital_agents"
    
    id: int = Column(Integer, primary_key=True)
    tenant_id: int = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    department_id: int = Column(Integer, ForeignKey("org_departments.id"), nullable=False)
    name: str = Column(String(100), nullable=False)           # 数字员工名称（可改）
    role: str = Column(String(100), default="")               # 角色描述（可改）
    avatar_color: str = Column(String(20), default="#1890FF") # 头像颜色
    status: str = Column(String(20), default="online")        # online/busy/offline
    description: str = Column(Text, default="")               # 详细介绍
    preset_id: str = Column(String(50), nullable=True)        # 预设标识
    created_at: datetime = Column(DateTime, default=utcnow)
    updated_at: datetime = Column(DateTime, default=utcnow, onupdate=utcnow)
```

### 2.3 员工（Employee）

```python
class Employee(Base):
    __tablename__ = "org_employees"
    
    id: int = Column(Integer, primary_key=True)
    tenant_id: int = Column(Integer, ForeignKey("tenants.id"), nullable=False)
    department_id: int = Column(Integer, ForeignKey("org_departments.id"), nullable=True)
    user_id: int = Column(Integer, ForeignKey("users.id"), nullable=True)  # 关联登录账号
    name: str = Column(String(100), nullable=False)
    phone: str = Column(String(20), nullable=True)
    title: str = Column(String(100), default="")              # 职位
    wecom_id: str = Column(String(100), nullable=True)        # 泛微用户 ID
    source: str = Column(String(20), default="manual")        # manual / wecom / import
    status: str = Column(String(20), default="active")        # active / inactive
    created_at: datetime = Column(DateTime, default=utcnow)
    updated_at: datetime = Column(DateTime, default=utcnow, onupdate=utcnow)
```

### 2.4 数字员工-Skill 关联（AgentSkill）

```python
class AgentSkill(Base):
    __tablename__ = "org_agent_skills"
    
    id: int = Column(Integer, primary_key=True)
    agent_id: int = Column(Integer, ForeignKey("org_digital_agents.id"), nullable=False)
    skill_id: int = Column(Integer, ForeignKey("org_skill_pool.id"), nullable=False)
    enabled: bool = Column(Boolean, default=True)             # 启用/停用
    assigned_at: datetime = Column(DateTime, default=utcnow)
    assigned_by: int = Column(Integer, nullable=True)         # 分配人 user_id
```

## 3. 预设 11 部门

| # | preset_id | 默认部门名 | 默认数字员工名 | 默认角色 | 默认技能 |
|---|-----------|-----------|--------------|---------|---------|
| 1 | dept_01 | 全能前台 | **笑笑** | AI 助手 | ddw.llm.chat, ddw.kb.search, ddw.email.send |
| 2 | dept_02 | 合规岗 | **法海** | 合规审查员 | ddw.legal.check, ddw.kb.search, ddw.esg.assess |
| 3 | dept_03 | 行政 | **邮友** | 邮件助理 | ddw.email.send, ddw.email.classify, ddw.reminder |
| 4 | dept_04 | 数据录入 | 数录 | 数据录入员 | ddw.ocr.invoice, ddw.ocr.contract |
| 5 | dept_05 | 流程审批 | 审批通 | 流程审批 | ddw.workflow.approve, ddw.email.send |
| 6 | dept_06 | 知识管理 | 知库 | 知识管理员 | ddw.kb.rebuild, ddw.kb.search |
| 7 | dept_07 | 销售部 | 销冠 | 销售助理 | ddw.sales.copilot, ddw.crm.search |
| 8 | dept_08 | 客服部 | 服星 | 客服专员 | ddw.online_cs.reply, ddw.ticket.create |
| 9 | dept_09 | 财务部 | 财审 | 财务审核 | ddw.finance.ocr, ddw.reconciliation |
| 10 | dept_10 | 人事部 | 人财 | HR 助理 | ddw.hris.sync, ddw.leave.approve |
| 11 | dept_11 | 研发 IT | 研思 | 研发助手 | ddw.code.review, ddw.tech.research |

> **注**：用户已确认前 3 个名称（笑笑/法海/邮友），后 8 个为占位，用户可随时修改。

## 4. API 端点

```yaml
# 部门
GET    /api/v1/org/departments                    # 列表（含数字员工数量）
GET    /api/v1/org/departments/{id}               # 详情（含数字员工 + 员工列表）
PUT    /api/v1/org/departments/{id}               # 修改名称/介绍（仅 company admin）
POST   /api/v1/org/departments                    # 新增部门（仅 company admin）

# 数字员工
GET    /api/v1/org/agents                         # 列表（可按 department_id 过滤）
GET    /api/v1/org/agents/{id}                    # 详情（含已分配 skill）
PUT    /api/v1/org/agents/{id}                    # 修改名称/角色/描述（company/dept admin）
POST   /api/v1/org/agents/{id}/skills             # 分配 skill（company/dept admin）
DELETE /api/v1/org/agents/{id}/skills/{skill_id}  # 移除 skill（company/dept admin）

# 员工
GET    /api/v1/org/employees                      # 列表（可按 department_id 过滤）
POST   /api/v1/org/employees                      # 新增员工
PUT    /api/v1/org/employees/{id}                 # 修改
DELETE /api/v1/org/employees/{id}                 # 移除
POST   /api/v1/org/employees/import               # 批量导入（CSV/Excel）
POST   /api/v1/org/wecom/sync-departments         # 从泛微同步部门
POST   /api/v1/org/wecom/sync-employees           # 从泛微同步员工
```

## 5. 前端页面

### 5.1 部门管理页（saas-admin.html#/org-departments）

- 卡片列表展示 11 个部门（含部门名、介绍、数字员工头像、员工数量）
- 点击卡片 → 展开详情 → 可编辑名称/介绍
- 公司级管理员：全部可编辑
- 部门级管理员：仅本部门可编辑
- 普通员工：只读

### 5.2 数字员工页（saas-admin.html#/org-agents）

- 卡片网格展示所有数字员工（按部门分组）
- 每个卡片：头像色块 + 名称 + 角色 + 状态指示灯 + 已分配 skill 标签
- 点击 → 详情页：修改名称/角色/描述 + skill 挑选面板（从 skill 池中勾选）
- skill 挑选面板：已分配 skill 列表（可启用/停用/移除） + 可选 skill 列表（可添加）

### 5.3 员工管理页（saas-admin.html#/org-employees）

- 表格展示：姓名/手机号/职位/部门/来源/状态/操作
- 操作：编辑/移除/分配到部门
- 导入按钮：上传 CSV（姓名,手机号,职位,部门）
- 泛微同步按钮：调 /api/v1/org/wecom/sync-employees（见 TASK_SPEC_WECOM_SYNC）

## 6. 权限矩阵

| 操作 | owner | dept admin | member |
|------|-------|-----------|--------|
| 查看所有部门 | ✅ | ✅（仅本部门详情） | ✅（仅列表） |
| 编辑部门名称/介绍 | ✅ | ❌ | ❌ |
| 新增部门 | ✅ | ❌ | ❌ |
| 查看数字员工 | ✅ | ✅（仅本部门） | ✅（仅列表） |
| 编辑数字员工 | ✅ | ✅（仅本部门） | ❌ |
| 分配/移除 skill | ✅ | ✅（仅本部门） | ❌ |
| 查看员工列表 | ✅ | ✅（仅本部门） | ❌ |
| 新增/编辑员工 | ✅ | ✅（仅本部门） | ❌ |
| 泛微同步 | ✅ | ❌ | ❌ |

## 7. 验收标准

| # | 验证项 | 预期结果 |
|---|--------|----------|
| 1 | 登录后进入 AI 组织 | 显示 11 个部门卡片 |
| 2 | 修改部门名称 | 刷新后保留新名称 |
| 3 | 数字员工详情 | 可修改名称 + 可从 skill 池挑选/移除 skill |
| 4 | 新增员工 | 填写姓名/手机号/职位/部门 → 保存成功 |
| 5 | CSV 导入 | 上传 CSV → 新增 N 个员工 |
| 6 | pytest | 全部新增测试通过 |

## 8. 依赖

- Skill 池插件（TASK_SPEC_SKILL_POOL）必须先就绪
- 泛微同步（TASK_SPEC_WECOM_SYNC）可后续迭代
