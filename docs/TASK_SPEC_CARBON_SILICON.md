# TASK_SPEC: 碳硅协作空间（零代码 DAG 流程设计器）

> 优先级：P1  
> 预计工时：2-3 周  
> 插件名：ddw_flow_designer  
> 状态：待确认  
> 前端：ReactFlow (@xyflow/react v12, MIT)  
> 后端：FastAPI + networkx

---

## 1. 概述

碳硅协作空间是 DDW 的零代码流程设计器，让企业员工通过拖拽方式设计数字员工和员工之间的 skill 协作流程。相当于一个企业级的可视化工作流引擎。

**核心价值**：不懂代码的业务人员也能设计复杂的 AI 协作流程。

## 2. 核心功能

| 功能 | 说明 |
|------|------|
| DAG 拖拽编辑器 | 基于 ReactFlow 的节点+连线编辑器 |
| 节点类型 | 数字员工节点 / Skill 节点 / 条件判断节点 / 开始节点 / 结束节点 |
| 连线 | 支持条件分支（if/else）和并行执行 |
| 草稿 | 随时保存未完成的流程 |
| 发布 | 正式发布，自动赋予版本号（vX.Y.Z） |
| 不保存删除 | 放弃当前修改 |
| 员工级流程 | 设计后立即可用/停用/修改 |
| 跨部门审核 | 涉及多部门的流程 → pending_review → 相关部门管理员审核 → published |
| 部门级不可删 | 部门管理员不能删除流程 |
| 公司级有限删除 | 仅可删除停用≥12个月的流程 |
| 公司级看板 | 只看统计，不可修改流程内容 |
| 版本管理 | 每次发布自动递增版本号，保留历史版本 |

## 3. 数据模型

### 3.1 流程定义（FlowDefinition）

```python
class FlowDefinition(Base):
    __tablename__ = "flow_definitions"
    
    id: int = Column(Integer, primary_key=True)
    tenant_id: int = Column(Integer, nullable=False)
    name: str = Column(String(200), nullable=False)
    description: str = Column(Text, default="")
    department_id: int = Column(Integer, nullable=True)       # 所属部门（null=公司级）
    created_by: int = Column(Integer, nullable=False)         # 创建人
    scope: str = Column(String(20), default="department")     # department / cross_department
    status: str = Column(String(30), default="draft")         # draft/pending_review/published/deprecated
    version: str = Column(String(20), default="0.0.0")        # semver
    dag_json: dict = Column(JSON, nullable=False)             # ReactFlow 的 nodes + edges JSON
    is_enabled: bool = Column(Boolean, default=False)         # 是否启用
    total_runs: int = Column(Integer, default=0)
    monthly_runs: int = Column(Integer, default=0)
    avg_duration_ms: int = Column(Integer, default=0)
    last_run_at: datetime = Column(DateTime, nullable=True)
    deprecated_at: datetime = Column(DateTime, nullable=True) # 进入 deprecated 的时间
    created_at: datetime = Column(DateTime, default=utcnow)
    updated_at: datetime = Column(DateTime, default=utcnow, onupdate=utcnow)
```

### 3.2 流程版本（FlowVersion）

```python
class FlowVersion(Base):
    __tablename__ = "flow_versions"
    
    id: int = Column(Integer, primary_key=True)
    flow_id: int = Column(Integer, ForeignKey("flow_definitions.id"), nullable=False)
    version: str = Column(String(20), nullable=False)         # v1.0.0, v1.1.0, ...
    dag_json: dict = Column(JSON, nullable=False)
    changelog: str = Column(Text, default="")
    published_by: int = Column(Integer, nullable=False)
    published_at: datetime = Column(DateTime, default=utcnow)
```

### 3.3 跨部门审核（FlowReview）

```python
class FlowReview(Base):
    __tablename__ = "flow_reviews"
    
    id: int = Column(Integer, primary_key=True)
    flow_id: int = Column(Integer, ForeignKey("flow_definitions.id"), nullable=False)
    department_id: int = Column(Integer, nullable=False)      # 需要审核的部门
    reviewer_id: int = Column(Integer, nullable=True)         # 审核人
    status: str = Column(String(20), default="pending")       # pending / approved / rejected
    comment: str = Column(Text, default="")
    reviewed_at: datetime = Column(DateTime, nullable=True)
```

## 4. 状态机

```
[草稿] ──发布──→ [待审核] ──所有部门审核通过──→ [已发布]
  │                  │                              │
  │                  │ 任一部门拒绝                  │ 停用
  │                  ↓                              ↓
  │              [已拒绝] ←────────────────── [已停用]
  │                  │                              │
  │                  └──修改后重新提交               │ 停用≥12个月
  │                                                 ↓
  └──────────────────────────────────────── [可删除]（仅公司级）

版本号规则：
  首次发布 → v1.0.0
  修改后重新发布 → v1.1.0（minor 递增）
  重大重构 → v2.0.0（major 递增，手动指定）
```

## 5. 节点类型

| 节点 | 图标 | 说明 | 配置项 |
|------|------|------|--------|
| 开始 | ▶️ | 流程入口 | 输入参数定义 |
| 数字员工 | 🤖 | 调用某数字员工 | 选择数字员工 + 输入映射 |
| Skill | ⚡ | 调用某 skill | 选择 skill + 参数映射 |
| 条件判断 | 🔀 | if/else 分支 | 条件表达式 |
| 并行 | 🔗 | 并行执行多分支 | 分支数量 |
| 合并 | 🔗 | 等待所有并行分支完成 | — |
| 结束 | ⏹️ | 流程出口 | 输出参数定义 |

## 6. API 端点

```yaml
# 流程
GET    /api/v1/flows                               # 列表
POST   /api/v1/flows                               # 创建（草稿）
GET    /api/v1/flows/{id}                          # 详情
PUT    /api/v1/flows/{id}                          # 修改（草稿状态）
DELETE /api/v1/flows/{id}                          # 删除（仅停用≥12个月+公司级）

# 版本
POST   /api/v1/flows/{id}/publish                  # 发布（自动递增版本号）
GET    /api/v1/flows/{id}/versions                  # 版本历史
GET    /api/v1/flows/{id}/versions/{version}        # 某版本详情

# 状态
PUT    /api/v1/flows/{id}/enable                   # 启用
PUT    /api/v1/flows/{id}/disable                  # 停用

# 审核
GET    /api/v1/flows/pending-reviews               # 待审核列表（部门管理员）
POST   /api/v1/flows/{id}/reviews/{review_id}      # 审核通过/拒绝

# 执行
POST   /api/v1/flows/{id}/run                      # 执行流程
GET    /api/v1/flows/{id}/runs                     # 执行历史

# 统计（公司级看板）
GET    /api/v1/flows/stats                         # 全公司流程统计
```

## 7. 前端页面

### 7.1 流程编辑器（carbon-silicon.html#/editor/{id}）

- 基于 ReactFlow 的全屏编辑器
- 左侧面板：可拖拽的节点类型（数字员工/Skill/条件/并行/合并）
- 中央画布：DAG 编辑区
- 右侧面板：选中节点的配置（数字员工选择/Skill 选择/条件表达式）
- 顶部工具栏：保存草稿 / 发布 / 不保存删除 / 版本历史
- 底部状态栏：当前版本号 / 最后保存时间 / 节点数 / 连线数

### 7.2 流程列表（carbon-silicon.html#/list）

- 表格：流程名 / 部门 / 作用域 / 状态 / 版本 / 调用次数 / 平均完成时长 / 最后使用 / 操作
- 操作：编辑 / 启用停用 / 查看版本历史 / 删除（如符合条件）

### 7.3 审核面板（carbon-silicon.html#/reviews）

- 部门管理员看到：待审核流程列表
- 每个流程：查看 DAG 预览 + 通过/拒绝按钮 + 审核意见

### 7.4 公司级看板（carbon-silicon.html#/dashboard）

- 流程总数 / 启用数 / 本月总调用次数
- 表格：所有流程的调用次数 / 月度调用 / 平均完成时长 / 最后使用时间
- **只读，不可修改任何流程内容**

## 8. 权限矩阵

| 操作 | member | dept admin | owner | chairman |
|------|--------|-----------|-------|----------|
| 创建流程 | ✅ | ✅ | ✅ | ❌ |
| 编辑自己的草稿 | ✅ | ✅ | ❌ | ❌ |
| 编辑本部门流程 | ❌ | ✅ | ❌ | ❌ |
| 发布（部门级） | ✅ | ✅ | ✅ | ❌ |
| 发布（跨部门） | ✅ | ✅ | ✅ | ❌ |
| 启用/停用 | ✅（自己的） | ✅（本部门） | ✅ | ❌ |
| 审核跨部门流程 | ✅（本部门） | ✅（本部门） | ✅ | ❌ |
| 删除 | ❌ | ❌ | ✅（停用≥12月） | ❌ |
| 查看看板 | ❌ | ✅（本部门） | ✅（全公司） | ✅（全公司） |

## 9. ReactFlow 集成方案

```html
<!-- carbon-silicon.html -->
<script src="https://unpkg.com/@xyflow/react@12/dist/index.js"></script>
<!-- 或 npm 打包 -->
```

- 自定义节点组件：`DigitalAgentNode`, `SkillNode`, `ConditionNode`, `StartNode`, `EndNode`
- 自定义边组件：支持条件标签
- dagre-d3 自动布局（节点拖拽后自动整理）
- 后端存储：dag_json = { nodes: [...], edges: [...] }

## 10. 验收标准

| # | 验证项 | 预期结果 |
|---|--------|----------|
| 1 | 拖拽创建流程 | 从左侧拖入节点，连线，保存草稿 |
| 2 | 发布 | 版本号从 v0.0.0 → v1.0.0 |
| 3 | 修改再发布 | 版本号 → v1.1.0 |
| 4 | 跨部门审核 | 流程进入 pending_review，部门管理员收到审核请求 |
| 5 | 审核通过 | 流程状态 → published |
| 6 | 执行流程 | 调用对应的数字员工/Skill |
| 7 | 公司级看板 | 显示所有流程统计，不可编辑 |
| 8 | 删除限制 | 停用<12个月的流程不可删除 |

## 11. 依赖

- npm: @xyflow/react v12 (MIT)
- Python: networkx（DAG 执行引擎）
- 前端打包：可用 Vite 或直接 CDN 引入

## 12. 文档与视频

- **操作手册**：Markdown 文档，含：节点类型说明 / 连接规则 / 审核流程 / 版本控制 / 常见场景 5 例
- **5 分钟视频脚本**：碳硅协作空间入门教程
- 文档路径：`docs/碳硅协作空间操作手册.md`
- 视频：待功能稳定后录制
