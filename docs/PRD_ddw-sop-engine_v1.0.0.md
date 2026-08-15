# PRD：ddw-sop-engine（状态机 SOP 编排引擎）v1.0.0

> 灵感来源：StaffDeck 的状态机驱动流程型技能（AGPL-3.0），DDW 为全新 Apache 2.0 实现
> 创建日期：2026-07-31
> 作者：Hermes Agent (DeepSeek V4 Pro) → 代码实现交由 MiMo Code CLI
> 依赖：PluginBase v2（需先完成 SDK-1: intervention_hooks）
> 许可证：Apache 2.0

---

## 零、产品概述

### 0.1 一句话定位

**ddw-sop-engine** 是一个让用户用自然语言描述业务流程，自动生成结构化 SOP（标准操作程序），并通过状态机保证流程准确执行的 DDW 插件引擎。

### 0.2 解决的痛点

| 痛点 | 现有方案 | ddw-sop-engine 方案 |
|:-----|:---------|:-------------------|
| 企业流程靠"口口相传" | 老员工离职 = 流程丢失 | SOP 固化为可执行状态机，永久保留 |
| AI Agent 执行复杂流程易出错 | Prompt Chain 无状态保证 | 状态机保证每一步的前置条件/后置验证 |
| 流程变更需改代码 | 修改 Python 代码重新部署 | 自然语言描述 → 自动生成 → 可视化编辑 → 热更新 |
| 多流程切换丢失上下文 | 每次重新开始 | 上下文保留 + 分支演化 + 版本管理 |

### 0.3 核心用户故事

1. **客服主管**：描述"客户投诉处理流程"→ 系统自动生成 SOP → 挂载到 ddw-smart-cs 客户角色 → AI 按 SOP 执行投诉处理
2. **IT 运维**：描述"服务器告警升级流程"→ 生成 SOP → 挂载定时任务 → 自动巡检 + 多级升级
3. **HR 经理**：描述"新员工入职流程"→ 生成 SOP → 挂载到企微 → 自动推送入职指引和表单

---

## 一、架构设计

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────┐
│                    用户接口层                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ REST API    │  │ WebSocket   │  │ IM 渠道     │  │
│  │ (CRUD SOP)  │  │ (实时状态)  │  │ (企微/微信) │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  │
├─────────┼────────────────┼────────────────┼─────────┤
│         ▼                ▼                ▼         │
│  ┌─────────────────────────────────────────────┐    │
│  │           SOP 引擎核心（本插件）              │    │
│  │                                              │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐   │    │
│  │  │ SOP      │  │ State    │  │ Context  │   │    │
│  │  │ Compiler │  │ Machine  │  │ Manager  │   │    │
│  │  │ (NL→JSON)│  │ (执行器) │  │ (上下文) │   │    │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘   │    │
│  │       │             │             │          │    │
│  │  ┌────▼─────────────▼─────────────▼─────┐    │    │
│  │  │         SOP Runtime Engine           │    │    │
│  │  │  (调度/分支/循环/并行/回滚/接管)      │    │    │
│  │  └────────────────┬────────────────────┘    │    │
│  └───────────────────┼─────────────────────────┘    │
├──────────────────────┼──────────────────────────────┤
│                      ▼                               │
│  ┌─────────────────────────────────────────────┐    │
│  │          DDW 插件生态（被编排对象）           │    │
│  │                                              │    │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌──────┐ │    │
│  │  │LLM     │ │Knowledge│ │Email  │ │HTTP  │ │    │
│  │  │Gateway │ │Hierarchy│ │Asst   │ │API   │ │    │
│  │  └────────┘ └────────┘ └────────┘ └──────┘ │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

### 1.2 核心设计原则

1. **状态机是执行保证，不是限制**：每个 SOP 节点有前置条件（guard）+ 后置验证（post-condition），但允许人工干预跳过
2. **自然语言→结构化 SOP 是辅助，不是替代**：LLM 生成初版，人工审核/编辑后再执行
3. **上下文跨节点保留**：不是每步重新调用 LLM，而是渐进式构建上下文栈
4. **版本不可变 + 分支可演化**：已发布的 SOP 版本不可修改，修改 = 新建分支

---

## 二、数据模型（SQLAlchemy ORM）

### 2.1 核心实体关系图

```
SOP (标准操作程序)
  ├── 1:N → SOPVersion (版本快照，不可变)
  │     └── 1:N → SOPNode (流程节点)
  │           ├── type: LLM_CALL | TOOL_CALL | CONDITION | LOOP | HUMAN_APPROVAL | PARALLEL | END
  │           ├── guards: [前置条件]
  │           ├── post_conditions: [后置验证]
  │           └── 1:N → SOPTransition (节点间转移)
  │                 ├── condition: 转移条件表达式
  │                 └── target_node_id
  │
  ├── 1:N → SOPInstance (运行实例)
  │     ├── current_node_id
  │     ├── context_stack: JSON (渐进式上下文)
  │     ├── execution_trace: JSON (完整执行轨迹)
  │     └── status: RUNNING | WAITING_APPROVAL | COMPLETED | FAILED | CANCELLED
  │
  └── N:M → Plugin (关联的 DDW 插件，提供 Tool)
```

### 2.2 完整 ORM 模型

```python
# models.py

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Text, DateTime, Boolean, Integer, Float,
    ForeignKey, JSON, Enum as SAEnum, Table, Index
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship
)
import enum

class Base(DeclarativeBase):
    """ORM 声明基类（SQLAlchemy 2.0 规范）。"""

# ─── 枚举 ───

class SOPStatus(str, enum.Enum):
    DRAFT = "draft"              # 草稿（可随意修改）
    REVIEW = "review"            # 审核中
    PUBLISHED = "published"      # 已发布（不可修改）
    DEPRECATED = "deprecated"    # 已废弃
    ARCHIVED = "archived"        # 已归档

class SOPNodeType(str, enum.Enum):
    LLM_CALL = "llm_call"           # 调用 LLM
    TOOL_CALL = "tool_call"         # 调用 DDW 插件 Tool
    CONDITION = "condition"         # 条件分支
    LOOP = "loop"                   # 循环
    HUMAN_APPROVAL = "human_approval"  # 人工审批
    PARALLEL = "parallel"           # 并行执行
    SUB_SOP = "sub_sop"             # 嵌套子 SOP
    START = "start"                 # 起始节点
    END = "end"                     # 结束节点

class InstanceStatus(str, enum.Enum):
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"

class ApprovalAction(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"
    MODIFY = "modify"
    SKIP = "skip"
    DELEGATE = "delegate"

# ─── 关联表 ───

sop_plugin_association = Table(
    'sop_plugin_association', Base.metadata,
    Column('sop_id', String(36), ForeignKey('sops.id'), primary_key=True),
    Column('plugin_name', String(128), primary_key=True),
)

# ─── SOP (主表) ───

class SOP(Base):
    __tablename__ = 'sops'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(256), nullable=False, index=True)
    description = Column(Text, nullable=True)
    category = Column(String(128), nullable=True, index=True)  # 如 "客服"/"运维"/"HR"
    tags = Column(JSON, nullable=True)  # ["投诉", "VIP客户", "退款"]
    
    # 关联
    creator_id = Column(String(36), nullable=False, index=True)
    current_version_id = Column(String(36), nullable=True)  # 指向当前活跃版本
    
    # 状态
    status = Column(SAEnum(SOPStatus), default=SOPStatus.DRAFT, index=True)
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    versions = relationship('SOPVersion', back_populates='sop',
                           foreign_keys='SOPVersion.sop_id',
                           order_by='SOPVersion.version_number.desc()')
    instances = relationship('SOPInstance', back_populates='sop')
    plugins = relationship('Plugin', secondary=sop_plugin_association, back_populates='sops')

    # 索引
    __table_args__ = (
        Index('idx_sop_status_category', 'status', 'category'),
        Index('idx_sop_creator', 'creator_id'),
    )

# ─── SOPVersion (版本快照，不可变) ───

class SOPVersion(Base):
    __tablename__ = 'sop_versions'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sop_id = Column(String(36), ForeignKey('sops.id'), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)  # 1, 2, 3...
    
    # 快照数据（JSON 格式，不可变）
    sop_snapshot = Column(JSON, nullable=False)  # 包含 name/description/category/tags
    nodes_snapshot = Column(JSON, nullable=False)  # 包含所有节点和转移的完整快照
    
    # 变更记录
    change_log = Column(Text, nullable=True)  # "新增审批节点；修改客服话术模板"
    parent_version_id = Column(String(36), nullable=True)  # 分支来源版本
    
    # 发布信息
    published_by = Column(String(36), nullable=True)
    published_at = Column(DateTime, nullable=True)
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    sop = relationship('SOP', back_populates='versions', foreign_keys=[sop_id])
    nodes = relationship('SOPNode', back_populates='version',
                        foreign_keys='SOPNode.version_id',
                        order_by='SOPNode.order_index')

    __table_args__ = (
        Index('idx_sopversion_sop_ver', 'sop_id', 'version_number', unique=True),
    )

# ─── SOPNode (流程节点) ───

class SOPNode(Base):
    __tablename__ = 'sop_nodes'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    version_id = Column(String(36), ForeignKey('sop_versions.id'), nullable=False, index=True)
    
    # 节点信息
    name = Column(String(256), nullable=False)
    description = Column(Text, nullable=True)
    node_type = Column(SAEnum(SOPNodeType), nullable=False)
    order_index = Column(Integer, nullable=False)  # 在流程图中的显示顺序
    
    # 节点配置（根据 node_type 不同，JSON schema 不同）
    config = Column(JSON, nullable=False)
    """
    LLM_CALL config:
    {
        "model": "miro-v2.5-pro",      // 模型名（走 DDW Gateway）
        "system_prompt": "你是客服...",
        "user_prompt_template": "客户说：{{context.user_message}}",
        "output_key": "ai_response",    // 输出存入上下文的 key
        "temperature": 0.7,
        "max_tokens": 2000,
        "fallback_nodes": ["node-xxx"]  // LLM 失败时的降级节点
    }
    
    TOOL_CALL config:
    {
        "plugin_name": "ddw-email-assistant",
        "tool_name": "send_email",
        "params_mapping": {             // 从上下文映射参数
            "to": "{{context.customer_email}}",
            "subject": "投诉回复：{{context.complaint_id}}",
            "body": "{{context.ai_response}}"
        },
        "output_key": "email_result",
        "timeout_seconds": 30,
        "retry_count": 3
    }
    
    CONDITION config:
    {
        "expression": "{{context.satisfaction_score}} >= 3",
        "true_node_id": "node-vip-handle",
        "false_node_id": "node-normal-handle"
    }
    
    LOOP config:
    {
        "loop_type": "while",           // while | for_each | until
        "condition": "{{context.retry_count}} < 3",
        "max_iterations": 10,
        "loop_body_nodes": ["node-xxx", "node-yyy"],
        "loop_variable": "retry_count"
    }
    
    HUMAN_APPROVAL config:
    {
        "approval_title": "退款审批",
        "approval_message_template": "客户 {{context.customer_name}} 申请退款 ¥{{context.amount}}，理由：{{context.reason}}",
        "approver_roles": ["admin", "finance_manager"],
        "timeout_minutes": 60,          // 超时自动处理
        "timeout_action": "reject",     // approve | reject | delegate
        "delegate_to_on_timeout": null,
        "approval_options": ["approve", "reject", "modify"],
        "modify_fields": ["amount"]     // 可修改的字段
    }
    
    PARALLEL config:
    {
        "parallel_nodes": ["node-a", "node-b", "node-c"],
        "wait_for": "all",              // all | any | first_n(3)
        "fail_fast": false,
        "max_concurrency": 5
    }
    
    SUB_SOP config:
    {
        "sub_sop_id": "sop-uuid-xxx",
        "sub_sop_version": 3,           // 可选，默认最新发布版
        "params_mapping": {
            "customer_id": "{{context.customer_id}}"
        },
        "wait_for_completion": true
    }
    """
    
    # 前后置条件（所有节点类型通用）
    guards = Column(JSON, nullable=True)
    """前置条件，例如:
    [{"field": "context.customer_email", "op": "not_empty"},
     {"field": "context.approval_status", "op": "eq", "value": "approved"}]
    支持操作符: eq, neq, gt, lt, gte, lte, in, not_in, not_empty, regex
    """
    
    post_conditions = Column(JSON, nullable=True)
    """后置验证，例如:
    [{"field": "output.ai_response", "op": "not_empty"},
     {"field": "output.ai_response", "op": "length_lt", "value": 5000}]
    """
    
    # 可视化坐标
    position_x = Column(Float, nullable=True)  # 流程图 X 坐标
    position_y = Column(Float, nullable=True)  # 流程图 Y 坐标
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    version = relationship('SOPVersion', back_populates='nodes', foreign_keys=[version_id])
    transitions_out = relationship('SOPTransition', back_populates='source_node',
                                  foreign_keys='SOPTransition.source_node_id')

    __table_args__ = (
        Index('idx_sopnode_version_order', 'version_id', 'order_index'),
    )

# ─── SOPTransition (节点间转移) ───

class SOPTransition(Base):
    __tablename__ = 'sop_transitions'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_node_id = Column(String(36), ForeignKey('sop_nodes.id'), nullable=False, index=True)
    target_node_id = Column(String(36), ForeignKey('sop_nodes.id'), nullable=False, index=True)
    
    # 转移条件
    condition_type = Column(String(32), default='always')  # always | expression | on_success | on_failure | on_timeout
    condition_expression = Column(Text, nullable=True)  # Jinja2 模板表达式
    priority = Column(Integer, default=0)  # 多条转移的优先级（数字越小优先级越高）
    label = Column(String(128), nullable=True)  # 在流程图上显示的标签，如 "满意 ✓" / "不满意 ✗"
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    source_node = relationship('SOPNode', back_populates='transitions_out',
                              foreign_keys=[source_node_id])
    
    __table_args__ = (
        Index('idx_soptrans_source_target', 'source_node_id', 'target_node_id'),
    )

# ─── SOPInstance (运行实例) ───

class SOPInstance(Base):
    __tablename__ = 'sop_instances'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sop_id = Column(String(36), ForeignKey('sops.id'), nullable=False, index=True)
    version_id = Column(String(36), ForeignKey('sop_versions.id'), nullable=False)
    
    # 运行状态
    status = Column(SAEnum(InstanceStatus), default=InstanceStatus.RUNNING, index=True)
    current_node_id = Column(String(36), ForeignKey('sop_nodes.id'), nullable=True)
    
    # 上下文栈（渐进式构建）
    context_stack = Column(JSON, default=dict)
    """
    上下文是分层的：
    {
        "init": {                         // 第 0 层：初始上下文
            "customer_id": "cust-123",
            "customer_name": "张三",
            "channel": "wecom"
        },
        "steps": [                        // 每步追加一层
            {
                "node_id": "node-xxx",
                "node_name": "意图识别",
                "input": {"user_message": "我要投诉"},
                "output": {"intent": "complaint", "confidence": 0.95},
                "duration_ms": 1200
            },
            {
                "node_id": "node-yyy",
                "node_name": "生成回复",
                "input": {"intent": "complaint"},
                "output": {"ai_response": "非常抱歉..."},
                "duration_ms": 3500
            }
        ],
        "pending_approvals": {            // 待审批项
            "node-zzz": {
                "approval_id": "appr-456",
                "requested_at": "2026-07-31T10:00:00Z",
                "timeout_at": "2026-07-31T11:00:00Z"
            }
        }
    }
    """
    
    # 完整执行 Trace
    execution_trace = Column(JSON, default=list)
    """
    [
        {
            "timestamp": "2026-07-31T10:00:00.000Z",
            "node_id": "node-xxx",
            "node_type": "llm_call",
            "event": "node_enter",
            "data": null
        },
        {
            "timestamp": "2026-07-31T10:00:01.200Z",
            "node_id": "node-xxx",
            "node_type": "llm_call",
            "event": "node_complete",
            "data": {
                "input_tokens": 500,
                "output_tokens": 200,
                "model": "mimo-v2.5-pro",
                "duration_ms": 1200
            }
        },
        ...
    ]
    """
    
    # 关联会话
    conversation_id = Column(String(36), nullable=True, index=True)  # 关联到 smart-cs 会话
    
    # 错误信息
    error_message = Column(Text, nullable=True)
    error_node_id = Column(String(36), nullable=True)
    retry_count = Column(Integer, default=0)
    
    # 时间戳
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    sop = relationship('SOP', back_populates='instances')
    
    __table_args__ = (
        Index('idx_sopinstance_sop_status', 'sop_id', 'status'),
        Index('idx_sopinstance_conversation', 'conversation_id'),
    )

# ─── ApprovalRecord (审批记录) ───

class ApprovalRecord(Base):
    __tablename__ = 'approval_records'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    instance_id = Column(String(36), ForeignKey('sop_instances.id'), nullable=False, index=True)
    node_id = Column(String(36), ForeignKey('sop_nodes.id'), nullable=False)
    
    # 审批内容
    title = Column(String(256), nullable=False)
    message = Column(Text, nullable=False)
    context_snapshot = Column(JSON, nullable=True)  # 审批时的上下文快照
    
    # 审批人
    requested_by = Column(String(36), nullable=False)
    approver_id = Column(String(36), nullable=True)
    approver_role = Column(String(64), nullable=True)
    
    # 审批结果
    action = Column(SAEnum(ApprovalAction), nullable=True)
    comment = Column(Text, nullable=True)
    modified_fields = Column(JSON, nullable=True)  # {"amount": 500} 审批人修改的字段
    
    # 超时
    timeout_at = Column(DateTime, nullable=True)
    timeout_action = Column(String(32), default='reject')
    
    # 时间戳
    requested_at = Column(DateTime, default=datetime.utcnow)
    responded_at = Column(DateTime, nullable=True)

# ─── Plugin (简化模型，实际走 DDW Plugin Registry) ───

class Plugin(Base):
    __tablename__ = 'sop_plugins'

    name = Column(String(128), primary_key=True)
    display_name = Column(String(256), nullable=False)
    version = Column(String(32), nullable=False)
    tools = Column(JSON, nullable=False)  # [{"name": "send_email", "description": "...", "params_schema": {...}}]
    
    sops = relationship('SOP', secondary=sop_plugin_association, back_populates='plugins')
```


> **SQLAlchemy 2.0 迁移说明**：以上 ORM 模型展示的是设计意图（字段名/类型/关系）。  
> 代码实现时必须使用 `Mapped[type]` + `mapped_column()` 语法（SQLAlchemy 2.0 规范），  
> 参考 `DDW_Plugin_Development_Guide.md` §5.1。

### 2.3 数据库迁移策略

- 使用 Alembic 自动生成迁移脚本
- 初始数据库：SQLite（开发/单机部署），支持通过 DDW 方言插件扩展为 PostgreSQL/MySQL
- JSON 字段在 SQLite 中以 TEXT 存储，PostgreSQL 中以 JSONB 存储
- 所有 `id` 字段使用 UUID v4（String(36)），避免自增 ID 冲突

---

## 三、API 端点设计（FastAPI Router）

### 3.1 端点清单

```python
# router.py

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Body
from typing import List, Optional

router = APIRouter(prefix="/api/v1/plugins/ddw-sop-engine", tags=["SOP Engine"])

# ─── 3.1 SOP CRUD ───

@router.post("/sops", response_model=SOPSchema, status_code=201)
async def create_sop(
    name: str = Body(..., description="SOP 名称"),
    description: str = Body(None, description="描述"),
    category: str = Body(None, description="分类"),
    tags: List[str] = Body(default=[]),
    natural_language_description: str = Body(None, description="自然语言流程描述（可选，LLM 自动生成初版）"),
    current_user = Depends(get_current_user),
) -> SOPSchema:
    """
    创建 SOP。
    如果提供 natural_language_description，自动调用 LLM 生成初版节点和转移。
    否则创建空的 SOP 框架。
    """

@router.get("/sops", response_model=List[SOPSchema])
async def list_sops(
    category: Optional[str] = Query(None),
    status: Optional[SOPStatus] = Query(None),
    search: Optional[str] = Query(None, description="按名称/描述搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user = Depends(get_current_user),
) -> PaginatedResponse[SOPSchema]:
    """列出 SOP，支持分页/筛选/搜索"""

@router.get("/sops/{sop_id}", response_model=SOPDetailSchema)
async def get_sop(
    sop_id: str = Path(...),
    current_user = Depends(get_current_user),
) -> SOPDetailSchema:
    """获取 SOP 详情（含当前版本的节点和转移）"""

@router.put("/sops/{sop_id}", response_model=SOPSchema)
async def update_sop(
    sop_id: str = Path(...),
    name: str = Body(None),
    description: str = Body(None),
    category: str = Body(None),
    tags: List[str] = Body(None),
    current_user = Depends(get_current_user),
) -> SOPSchema:
    """更新 SOP 元数据（不更新版本）"""

@router.delete("/sops/{sop_id}", status_code=204)
async def delete_sop(
    sop_id: str = Path(...),
    current_user = Depends(get_current_user),
):
    """删除 SOP（仅 DRAFT 状态可删除）"""

# ─── 3.2 SOP 版本管理 ───

@router.get("/sops/{sop_id}/versions", response_model=List[SOPVersionSchema])
async def list_versions(
    sop_id: str = Path(...),
    current_user = Depends(get_current_user),
) -> List[SOPVersionSchema]:
    """列出 SOP 的所有版本"""

@router.post("/sops/{sop_id}/versions", response_model=SOPVersionSchema, status_code=201)
async def create_version(
    sop_id: str = Path(...),
    change_log: str = Body(...),
    nodes: List[NodeSchema] = Body(..., description="完整的节点列表"),
    transitions: List[TransitionSchema] = Body(default=[]),
    parent_version_id: str = Body(None, description="分支来源版本 ID"),
    current_user = Depends(get_current_user),
) -> SOPVersionSchema:
    """
    创建新版本。
    传入完整的节点和转移列表（前端编辑后的结果）。
    自动递增版本号。
    如果 parent_version_id 不为空，标记为分支版本。
    """

@router.post("/sops/{sop_id}/versions/{version_id}/publish", response_model=SOPVersionSchema)
async def publish_version(
    sop_id: str = Path(...),
    version_id: str = Path(...),
    current_user = Depends(get_current_user),
) -> SOPVersionSchema:
    """发布版本（状态：DRAFT → PUBLISHED，标记为当前活跃版本）"""

@router.get("/sops/{sop_id}/versions/{version_id}/diff")
async def diff_versions(
    sop_id: str = Path(...),
    version_id: str = Path(...),
    compare_with: str = Query(..., description="对比版本 ID"),
    current_user = Depends(get_current_user),
) -> DiffSchema:
    """对比两个版本的差异"""

# ─── 3.3 节点与转移管理 ───

@router.post("/versions/{version_id}/nodes", response_model=NodeSchema, status_code=201)
async def add_node(
    version_id: str = Path(...),
    node: NodeCreateSchema = Body(...),
    current_user = Depends(get_current_user),
) -> NodeSchema:
    """向版本添加节点"""

@router.put("/nodes/{node_id}", response_model=NodeSchema)
async def update_node(
    node_id: str = Path(...),
    node: NodeUpdateSchema = Body(...),
    current_user = Depends(get_current_user),
) -> NodeSchema:
    """更新节点（含 config / guards / post_conditions）"""

@router.delete("/nodes/{node_id}", status_code=204)
async def delete_node(node_id: str = Path(...)):
    """删除节点（级联删除关联转移）"""

@router.post("/transitions", response_model=TransitionSchema, status_code=201)
async def add_transition(
    transition: TransitionCreateSchema = Body(...),
    current_user = Depends(get_current_user),
) -> TransitionSchema:
    """添加节点间转移"""

@router.delete("/transitions/{transition_id}", status_code=204)
async def delete_transition(transition_id: str = Path(...)):
    """删除转移"""

# ─── 3.4 LLM 辅助生成 ───

@router.post("/sops/generate-from-nl", response_model=GenerateResultSchema)
async def generate_sop_from_nl(
    natural_language: str = Body(..., description="自然语言流程描述，如：客户投诉后先识别意图..."),
    category: str = Body(None),
    current_user = Depends(get_current_user),
) -> GenerateResultSchema:
    """
    从自然语言生成 SOP 框架。
    
    LLM 输出格式：
    {
        "name": "客户投诉处理流程",
        "description": "...",
        "nodes": [
            {"name": "意图识别", "type": "llm_call", "config": {...}},
            {"name": "判断投诉类型", "type": "condition", "config": {...}},
            ...
        ],
        "transitions": [
            {"from": "node-0", "to": "node-1", "condition": "on_success"},
            ...
        ]
    }

    SOP 编译为节点 + 转移。
    节点的 type 为 START | LLM_CALL | CONDITION | HUMAN_APPROVAL | END。
    返回的 JSON 包含完整的节点和转移列表，前端可直接渲染流程图。
    """

    Args:
        natural_language: str - 自然语言流程描述
        category: Optional[str] - 分类(用于预设提示模板)

    Returns:
        GenerateResultSchema: 节点 + 转移 + 名称 + 描述

    Note:
        调用 LLM Gateway, 使用 SOP 专用提示模板。
        处理失败时返回 422 错误及建议修正文本。

@router.post("/sops/{sop_id}/suggest-improvement", response_model=SuggestResultSchema)
async def suggest_improvement(
    sop_id: str = Path(...),
    current_user = Depends(get_current_user),
) -> SuggestResultSchema:
    """
    基于 SOP 执行历史，LLM 分析并建议改进点。
    分析维度：瓶颈节点（平均耗时最长）、高失败率节点、可并行化的串行节点。
    """

# ─── 3.5 实例执行 ───

@router.post("/sops/{sop_id}/execute", response_model=InstanceSchema, status_code=201)
async def execute_sop(
    sop_id: str = Path(...),
    version_id: str = Body(None, description="指定版本，默认最新发布版"),
    init_context: dict = Body(default={}, description="初始上下文"),
    conversation_id: str = Body(None),
    async_mode: bool = Body(default=True, description="异步执行（默认 true）"),
    current_user = Depends(get_current_user),
) -> InstanceSchema:
    """
    启动 SOP 执行。
    
    执行模式：
    - 异步（async_mode=True）：立即返回 instance_id，执行在后台继续。前端通过 WebSocket 订阅实时状态。
    - 同步（async_mode=False）：阻塞等待 SOP 完成或遇到人工审批节点时暂停。
    
    遇到 HUMAN_APPROVAL 节点时：
    - 实例状态变为 WAITING_APPROVAL
    - 创建 ApprovalRecord
    - 通过 WebSocket 推送审批通知到前端
    - 审批完成后继续执行
    """

@router.get("/instances/{instance_id}", response_model=InstanceDetailSchema)
async def get_instance(
    instance_id: str = Path(...),
    current_user = Depends(get_current_user),
) -> InstanceDetailSchema:
    """获取运行实例详情（含当前节点/上下文/Trace）"""

@router.get("/instances", response_model=List[InstanceSchema])
async def list_instances(
    sop_id: Optional[str] = Query(None),
    status: Optional[InstanceStatus] = Query(None),
    conversation_id: Optional[str] = Query(None),
    page: int = Query(1),
    page_size: int = Query(20),
    current_user = Depends(get_current_user),
) -> PaginatedResponse[InstanceSchema]:
    """列出运行实例"""

@router.post("/instances/{instance_id}/pause", response_model=InstanceSchema)
async def pause_instance(instance_id: str = Path(...)):
    """暂停实例执行（当前节点完成后暂停）"""

@router.post("/instances/{instance_id}/resume", response_model=InstanceSchema)
async def resume_instance(instance_id: str = Path(...)):
    """恢复实例执行"""

@router.post("/instances/{instance_id}/cancel", response_model=InstanceSchema)
async def cancel_instance(instance_id: str = Path(...)):
    """取消实例执行"""

@router.post("/instances/{instance_id}/retry", response_model=InstanceSchema)
async def retry_instance(
    instance_id: str = Path(...),
    from_node_id: str = Body(None, description="从指定节点重试，默认从失败节点"),
):
    """重试失败的实例"""

# ─── 3.6 人工干预（介入钩子） ───

@router.post("/instances/{instance_id}/intervene", response_model=InstanceSchema)
async def intervene_instance(
    instance_id: str = Path(...),
    action: str = Body(..., description="skip_node | jump_to | modify_context | force_continue"),
    target_node_id: str = Body(None, description="跳转目标节点 ID（jump_to 时需要）"),
    context_updates: dict = Body(None, description="上下文修改（modify_context 时需要）"),
    current_user = Depends(get_current_user),
):
    """
    人工干预运行中的实例。
    
    - skip_node: 跳过当前节点（忽略其输出，继续下一节点）
    - jump_to: 跳转到指定节点
    - modify_context: 修改实例上下文
    - force_continue: 强制继续（忽略 guard 失败）
    """

# ─── 3.7 审批操作 ───

@router.post("/approvals/{approval_id}/respond", response_model=ApprovalRecordSchema)
async def respond_approval(
    approval_id: str = Path(...),
    action: ApprovalAction = Body(...),
    comment: str = Body(None),
    modified_fields: dict = Body(None),
    current_user = Depends(get_current_user),
):
    """
    审批人回复审批请求。
    审批通过/驳回/修改后，SOP 实例自动继续执行。
    """

@router.get("/approvals/pending", response_model=List[ApprovalRecordSchema])
async def list_pending_approvals(
    current_user = Depends(get_current_user),
) -> List[ApprovalRecordSchema]:
    """列出当前用户的所有待审批项"""

# ─── 3.8 WebSocket 实时推送 ───

@router.websocket("/ws/instances/{instance_id}")
async def websocket_instance(websocket: WebSocket, instance_id: str):
    """
    WebSocket 端点。
    推送事件：
    - node_enter: {node_id, node_name, node_type, timestamp}
    - node_complete: {node_id, output, duration_ms, timestamp}
    - approval_required: {approval_id, title, message}
    - instance_paused: {reason, timestamp}
    - instance_completed: {result, total_duration_ms, timestamp}
    - instance_failed: {error, failed_node_id, timestamp}
    """

# ─── 3.9 统计分析 ───

@router.get("/sops/{sop_id}/stats", response_model=SOPStatsSchema)
async def get_sop_stats(
    sop_id: str = Path(...),
    days: int = Query(30, ge=1, le=365),
    current_user = Depends(get_current_user),
) -> SOPStatsSchema:
    """
    SOP 执行统计。
    返回：总执行次数、成功率、平均耗时、各节点耗时分布、失败热点。
    """
```

---

## 四、状态机执行引擎设计

### 4.1 核心执行循环

```python
# engine.py (伪代码，完整实现由 MiMo Code 完成)

class SOPRuntimeEngine:
    """
    SOP 运行时引擎。
    负责：节点调度、条件评估、上下文管理、Trace 记录、干预响应。
    """

    def __init__(self, instance: SOPInstance, llm_gateway, plugin_registry):
        self.instance = instance
        self.llm = llm_gateway
        self.registry = plugin_registry
        self._paused = False
        self._cancelled = False

    async def run(self):
        """主执行循环"""
        current = await self._get_node(self.instance.current_node_id)
        
        while current and not self._cancelled:
            # 1. 检查暂停标志
            if self._paused:
                await self._wait_for_resume()
            
            # 2. 执行节点
            try:
                output = await self._execute_node(current)
            except NodeExecutionError as e:
                await self._handle_error(current, e)
                return
            
            # 3. 评估转移条件
            next_node = await self._evaluate_transitions(current, output)
            
            # 4. 更新实例
            await self._advance(current, next_node, output)
            
            # 5. 如果是审批节点，暂停等待
            if current.node_type == SOPNodeType.HUMAN_APPROVAL:
                await self._wait_for_approval(current)
            
            current = next_node

    async def _execute_node(self, node: SOPNode) -> dict:
        """根据节点类型分发执行"""
        handlers = {
            SOPNodeType.LLM_CALL: self._exec_llm_call,
            SOPNodeType.TOOL_CALL: self._exec_tool_call,
            SOPNodeType.CONDITION: self._exec_condition,
            SOPNodeType.LOOP: self._exec_loop,
            SOPNodeType.HUMAN_APPROVAL: self._exec_human_approval,
            SOPNodeType.PARALLEL: self._exec_parallel,
            SOPNodeType.SUB_SOP: self._exec_sub_sop,
            SOPNodeType.START: self._exec_start,
            SOPNodeType.END: self._exec_end,
        }
        handler = handlers.get(node.node_type)
        if not handler:
            raise ValueError(f"Unknown node type: {node.node_type}")
        
        # 检查前置条件
        if node.guards:
            self._check_guards(node.guards)
        
        # 执行
        result = await handler(node)
        
        # 检查后置条件
        if node.post_conditions:
            self._check_post_conditions(node.post_conditions, result)
        
        return result

    async def _exec_llm_call(self, node: SOPNode) -> dict:
        """执行 LLM 调用节点"""
        config = node.config
        # 1. 从上下文渲染 prompt 模板
        system_prompt = self._render_template(config['system_prompt'])
        user_prompt = self._render_template(config['user_prompt_template'])
        
        # 2. 调用 LLM Gateway
        response = await self.llm.chat(
            model=config.get('model', 'mimo-v2.5-pro'),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=config.get('temperature', 0.7),
            max_tokens=config.get('max_tokens', 2000),
        )
        
        # 3. 存入上下文
        output_key = config.get('output_key', f'node_{node.id}_output')
        return {output_key: response.content}

    async def _exec_tool_call(self, node: SOPNode) -> dict:
        """执行插件 Tool 调用"""
        config = node.config
        plugin_name = config['plugin_name']
        tool_name = config['tool_name']
        
        # 1. 从上下文渲染参数
        params = {}
        for key, template in config.get('params_mapping', {}).items():
            params[key] = self._render_template(template)
        
        # 2. 获取插件 Tool
        plugin = self.registry.get_plugin(plugin_name)
        tool = plugin.get_tool(tool_name)
        
        # 3. 执行（带重试）
        for attempt in range(config.get('retry_count', 1) + 1):
            try:
                result = await asyncio.wait_for(
                    tool.execute(**params),
                    timeout=config.get('timeout_seconds', 30)
                )
                break
            except asyncio.TimeoutError:
                if attempt == config.get('retry_count', 1):
                    raise NodeExecutionError(f"Tool {tool_name} timeout")
            except Exception as e:
                if attempt == config.get('retry_count', 1):
                    raise NodeExecutionError(f"Tool {tool_name} failed: {e}")
        
        output_key = config.get('output_key', f'tool_{node.id}_output')
        return {output_key: result}

    async def _exec_condition(self, node: SOPNode) -> dict:
        """执行条件分支节点"""
        config = node.config
        expression = self._render_template(config['expression'])
        
        # 安全的表达式求值（使用 restrictedpython 或自定义解析器）
        result = self._safe_eval(expression)
        
        return {'condition_result': result}

    async def _exec_loop(self, node: SOPNode) -> dict:
        """执行循环节点"""
        config = node.config
        loop_type = config['loop_type']
        max_iterations = config.get('max_iterations', 10)
        
        results = []
        for i in range(max_iterations):
            # 检查循环条件
            if loop_type == 'while':
                condition = self._render_template(config['condition'])
                if not self._safe_eval(condition):
                    break
            
            # 执行循环体节点
            for body_node_id in config['loop_body_nodes']:
                body_node = await self._get_node(body_node_id)
                output = await self._execute_node(body_node)
                results.append(output)
        
        return {'loop_results': results, 'iterations': len(results)}

    async def _exec_human_approval(self, node: SOPNode) -> dict:
        """触达人工审批"""
        config = node.config
        
        # 创建审批记录
        approval = await self._create_approval(
            title=self._render_template(config['approval_title']),
            message=self._render_template(config['approval_message_template']),
            node_id=node.id,
        )
        
        # 推送 WebSocket 通知
        await self._notify_approval_required(approval)
        
        # 暂停实例
        self.instance.status = InstanceStatus.WAITING_APPROVAL
        await self._save_instance()
        
        # 等待审批（异步模式：返回；同步模式：阻塞）
        result = await self._wait_for_approval_response(approval)
        
        return {'approval_result': result}

    async def _exec_parallel(self, node: SOPNode) -> dict:
        """并行执行多个子节点"""
        config = node.config
        parallel_nodes = config['parallel_nodes']
        max_concurrency = config.get('max_concurrency', 5)
        
        semaphore = asyncio.Semaphore(max_concurrency)
        
        async def exec_with_semaphore(node_id):
            async with semaphore:
                child_node = await self._get_node(node_id)
                return await self._execute_node(child_node)
        
        tasks = [exec_with_semaphore(nid) for nid in parallel_nodes]
        
        wait_for = config.get('wait_for', 'all')
        if wait_for == 'all':
            results = await asyncio.gather(*tasks, return_exceptions=True)
        elif wait_for == 'any':
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            results = [task.result() for task in done]
        
        return {'parallel_results': results}

    async def _exec_sub_sop(self, node: SOPNode) -> dict:
        """执行嵌套子 SOP"""
        config = node.config
        sub_sop_id = config['sub_sop_id']
        
        # 创建子 SOP 实例
        sub_instance = await self._create_sub_instance(
            sop_id=sub_sop_id,
            init_context=self._render_params(config.get('params_mapping', {})),
        )
        
        # 执行子 SOP
        sub_engine = SOPRuntimeEngine(sub_instance, self.llm, self.registry)
        await sub_engine.run()
        
        return {'sub_sop_instance_id': sub_instance.id, 'result': sub_instance.context_stack}

    # ─── 辅助方法 ───

    def _render_template(self, template: str) -> str:
        """使用 Jinja2 渲染模板，从 context_stack 取值"""
        if not template:
            return template
        from jinja2 import Template
        context = self._flatten_context()
        return Template(template).render(context=context)

    def _flatten_context(self) -> dict:
        """将分层上下文展平为单层字典"""
        flat = dict(self.instance.context_stack.get('init', {}))
        for step in self.instance.context_stack.get('steps', []):
            if step.get('output'):
                flat.update(step['output'])
        return flat

    def _check_guards(self, guards: list):
        """检查前置条件，失败抛出 GuardViolationError"""
        context = self._flatten_context()
        for guard in guards:
            field = self._render_template(guard['field'])
            op = guard['op']
            value = guard.get('value')
            
            actual = context.get(field)
            
            checks = {
                'not_empty': lambda: actual is not None and actual != '',
                'eq': lambda: actual == value,
                'neq': lambda: actual != value,
                'gt': lambda: float(actual) > float(value),
                'lt': lambda: float(actual) < float(value),
                'gte': lambda: float(actual) >= float(value),
                'lte': lambda: float(actual) <= float(value),
                'in': lambda: actual in value,
                'not_in': lambda: actual not in value,
                'regex': lambda: re.match(value, str(actual)),
                'length_lt': lambda: len(str(actual)) < int(value),
            }
            
            check_fn = checks.get(op)
            if check_fn and not check_fn():
                raise GuardViolationError(
                    f"Guard failed: {field} {op} {value}, actual={actual}"
                )

    def _safe_eval(self, expression: str) -> bool:
        """安全的表达式求值，仅支持简单比较和逻辑运算"""
        # 使用 ast.literal_eval 或 simpleeval 库
        import ast
        try:
            context = self._flatten_context()
            # 简单的 Jinja2 模板求值后的字符串转布尔
            # 完整的实现使用 simpleeval 库
            return bool(eval(expression, {"__builtins__": {}}, context))
        except Exception:
            return False
```

### 4.2 状态转移表

| 当前状态 | 事件 | 下一状态 | 说明 |
|:---------|:-----|:---------|:-----|
| RUNNING | node_complete (非审批) | RUNNING | 正常执行下一节点 |
| RUNNING | node_complete (审批) | WAITING_APPROVAL | 遇到审批节点 |
| RUNNING | node_complete (END) | COMPLETED | SOP 完成 |
| RUNNING | pause_requested | PAUSED | 用户暂停 |
| RUNNING | cancel_requested | CANCELLED | 用户取消 |
| RUNNING | error_occurred | FAILED | 执行错误 |
| WAITING_APPROVAL | approval_responded | RUNNING | 审批完成继续 |
| WAITING_APPROVAL | approval_timeout | RUNNING (执行 timeout_action) | 审批超时 |
| WAITING_APPROVAL | cancel_requested | CANCELLED | 等待审批时取消 |
| PAUSED | resume_requested | RUNNING | 用户恢复 |
| PAUSED | cancel_requested | CANCELLED | 暂停时取消 |
| FAILED | retry_requested | RUNNING | 用户重试 |
| FAILED | cancel_requested | CANCELLED | 失败后取消 |

---

## 五、前端交互设计

### 5.1 可视化 SOP 编辑器

**技术选型**：React Flow (reactflow.dev) — MIT 许可，与 DDW 的 React/TypeScript 前端兼容。

**功能清单**：
1. 拖拽节点类型到画布（LLM调用/工具调用/条件/循环/审批/并行/子SOP）
2. 连线创建转移（拖拽节点输出端口到目标节点输入端口）
3. 双击节点弹出配置面板（根据节点类型显示不同的配置表单）
4. 实时验证：保存前检查是否有孤立节点、死循环、未配置的必填字段
5. 版本历史时间线：左侧面板展示所有版本，点击切换查看
6. "从自然语言生成"按钮：弹出文本框 → LLM 生成 → 自动渲染到画布

### 5.2 执行监控面板

1. 当前执行节点高亮（绿色边框 + 呼吸动画）
2. 已完成节点灰色 + ✓ 标记
3. 失败节点红色 + ✗ 标记 + 错误详情 tooltip
4. 审批节点黄色 + ⏳ 标记 + 点击查看审批详情
5. 右侧面板：上下文查看器（JSON 树）、Trace 时间线
6. 底部操作栏：暂停/恢复/取消/重试/强制跳转

---

## 六、集成点

### 6.1 与 ddw-llm-gateway 集成

- SOP 的 LLM_CALL 节点通过 DDW Gateway 调用 LLM
- 自动记录 Token 消耗到 ddw-token-manager
- 支持故障转移（fallback_nodes）

### 6.2 与 ddw-smart-cs 集成

- 客服会话可绑定 SOP Instance
- 客户消息 → 触发 SOP 节点执行
- SOP 的 HUMAN_APPROVAL 节点 → 推送审批到客服主管企微

### 6.3 与 ddw-adapter-registry 集成

- 审批通知通过 IM 适配器推送（企微/微信/飞书/钉钉）
- 审批人可通过 IM 回复审批（"同意"/"驳回"）

### 6.4 与 PluginBase v2 (intervention_hooks) 集成

```python
# 在 PluginBase v2 中新增的钩子接口
class InterventionHooks:
    async def on_sop_node_enter(self, instance_id: str, node: dict) -> None: ...
    async def on_sop_node_complete(self, instance_id: str, node: dict, output: dict) -> None: ...
    async def on_sop_approval_required(self, instance_id: str, approval: dict) -> None: ...
    async def on_sop_instance_completed(self, instance_id: str, result: dict) -> None: ...
    async def on_sop_instance_failed(self, instance_id: str, error: dict) -> None: ...
```

---

## 七、测试计划

### 7.1 单元测试（目标覆盖率 ≥ 90%）

| 测试模块 | 测试文件 | 关键用例 |
|:---------|:---------|:---------|
| SOP CRUD | `test_sop_crud.py` | 创建/读取/更新/删除/列表/分页/搜索/状态流转 |
| 版本管理 | `test_sop_version.py` | 创建版本/发布/对比差异/版本列表/分支版本 |
| LLM 生成 | `test_sop_generate.py` | 自然语言→SOP 编译/提示模板/错误处理 |
| 状态机引擎 | `test_engine.py` | 线性流程/条件分支/循环/并行/子SOP/审批暂停恢复 |
| 上下文管理 | `test_context.py` | 模板渲染/分层上下文/上下文修改 |
| 干预钩子 | `test_intervention.py` | 跳过节点/强制跳转/修改上下文/强制继续 |
| 审批流程 | `test_approval.py` | 创建审批/审批通过/驳回/修改/超时处理 |
| Guard 验证 | `test_guards.py` | 各种操作符的正确/失败场景 |
| WebSocket | `test_websocket.py` | 实时推送/重连/多客户端 |

### 7.2 集成测试

1. SOP 引擎 + LLM Gateway：完整执行一个 LLM_CALL 节点
2. SOP 引擎 + Email Assistant：SOP 中调用发送邮件 Tool
3. SOP 引擎 + Smart CS：客服会话绑定 SOP，完整对话流程
4. 审批超时：模拟审批超时自动处理

### 7.3 性能测试

| 场景 | 目标 |
|:-----|:-----|
| 单节点执行延迟 | < 100ms（不含 LLM 调用时间） |
| 100 并发实例 | 无崩溃，P95 < 500ms |
| 1000 节点 SOP 加载 | < 1s |
| 审批通知推送延迟 | < 2s |

---

## 八、部署与配置

### 8.1 manifest.yaml（DDW 规范 §4 格式）

```yaml
name: ddw-sop-engine
version: 1.0.0
description: "状态机驱动的 SOP 编排引擎"
author: DDW Team
license: Apache-2.0
engine: ">=2.0.0"
isolation: inline

permissions:
  - "database:ddw_sop_engine"
  - "api:ddw-llm-gateway:read"
  - "api:ddw-adapter-registry:read"

dependencies:
  plugins:
    ddw-llm-gateway: ">=1.0.0"
  python:
    - fastapi>=0.110
    - sqlalchemy>=2.0
    - jinja2>=3.1
    - pydantic>=2.0

events:
  produces:
    - "sop.instance.started"
    - "sop.instance.completed"
    - "sop.instance.failed"
    - "sop.node.executed"
    - "sop.approval.required"
  consumes:
    - "user.message.received"

config:
  optional:
    default_llm_model: "mimo-v2.5-pro"
    max_concurrent_instances: 50
    approval_timeout_minutes: 60
    execution_trace_retention_days: 90

ecosystem:
  category: "core-engine"
  tags: ["sop", "workflow", "state-machine", "orchestration"]

quality:
  ai_output:
    required: false
    max_hallucination_rate: 0.05
```

### 8.2 启动依赖顺序

```
1. ddw-llm-gateway (必须)
2. ddw-token-manager (可选，用于 Token 统计)
3. ddw-adapter-registry (可选，用于审批通知)
4. ddw-sop-engine ← 本插件
```

---

## 九、安全与权限

| 维度 | 措施 |
|:-----|:-----|
| SOP CRUD | 创建者/管理员可编辑，其他用户只读 |
| 版本发布 | 仅审核角色可发布 |
| 实例执行 | 仅 SOP 创建者/管理员可手动干预 |
| 审批操作 | 仅指定审批角色可回复审批 |
| LLM 调用 | 所有 LLM 调用走 DDW Gateway 统一鉴权 |
| Tool 调用 | 继承被调用插件的权限模型 |
| Trace 数据 | 仅管理员可查看完整 Trace（含 prompt 内容） |

---



## X. 插件入口（DDW 规范要求）

### register(app) 注册函数

```python
# __init__.py
PLUGIN_NAME = "ddw-sop-engine"
PLUGIN_VERSION = "1.0.0"

def register(app, config=None):
    """DDW 平台调用此函数挂载插件路由。"""
    from .router import router
    app.include_router(
        router,
        prefix=f"/api/v1/plugins/{PLUGIN_NAME}",
        tags=[PLUGIN_NAME],
    )
```

### 标准健康检查端点

```python
# router.py 中必须包含
@router.get("/health")
async def health():
    return {
        "plugin": PLUGIN_NAME,
        "status": "ok",
        "version": PLUGIN_VERSION,
        "endpoints": [
            "/sops",
            "/sops/{sop_id}/versions",
            "/sops/{sop_id}/execute",
            "/instances/{instance_id}",
            "/approvals/pending",
            "/ws/instances/{instance_id}",
        ],
    }
```

### 资源消耗声明（DDW 规范 §5.4）

| 维度 | 评估值 |
|:-----|:------|
| CPU 常态负载 | 10-15%（单请求 <100ms 不含 LLM） |
| CPU 峰值负载 | 40%（50 并发实例） |
| 基础内存 | 80 MB（插件加载 + 路由注册 + 配置） |
| 运行时内存 | 256 MB（单实例上下文 + 并发） |
| 峰值内存 | 512 MB（50 并发 + 审批缓存） |
| 代码体积 | 120 KB（预估，含 ORM + 引擎 + 路由） |
| 数据库存储 | 10 MB/月（1000 实例/天 × 90 天 Trace） |
| LLM Token | 每次 SOP 执行消耗取决于节点数（见 §2.2 config） |
| 最大并发 | 50 实例（推荐配置） |
| 必需依赖 | ddw-llm-gateway |
| 可选依赖 | ddw-token-manager, ddw-adapter-registry |
| 资源评级 | **中等级**（需 LLM Gateway 作为外部依赖） |

## 十、灵感溯源与合规声明

- **灵感来源**：StaffDeck（OpenBMB，AGPL-3.0）的"状态机驱动的流程型技能"概念——自然语言生成结构化 SOP、状态机保证准确执行、人工审批节点集成
- **DDW 实现**：全新 Apache 2.0 实现。状态机引擎基于 W3C SCXML 标准设计，SOP 编译器和执行引擎完全自主开发。未复制 StaffDeck 任何源码、注释、变量名或函数签名
- **差异化**：DDW SOP 引擎的并行执行、子 SOP 嵌套、Guard 前置条件验证、WebSocket 实时推送均为 StaffDeck 不具备的特性
- **认证**：如未来通过 API 与 StaffDeck 实例通信（连接器模式），将严格遵循 DDW 已有的 AGPL 合规模板

---

*本文档为 PRD 初稿。代码实现由 MiMo Code CLI（32G Mac mini，00:00-08:00 折扣窗口）执行，DeepSeek V4 Flash（128G MBP，ds4-server）负责代码审查。*
