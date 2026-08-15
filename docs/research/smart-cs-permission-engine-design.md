# DDW 权限引擎插件（ddw-permission-engine）技术方案

> **日期**：2026-07-13
> **版本**：v1.0
> **定位**：所有业务插件的公共权限底座
> **核心技术**：Casbin 20,236⭐（Apache 2.0）
> **参考实现**：Casdoor 13,923⭐（Apache 2.0）身份源对接模式

---

## 目录

1. [设计原则与技术选型](#1-设计原则与技术选型)
2. [插件架构设计](#2-插件架构设计)
3. [Casbin 模型设计](#3-casbin-模型设计)
4. [数据模型设计](#4-数据模型设计)
5. [API 端点设计](#5-api-端点设计)
6. [业务插件集成方式](#6-业务插件集成方式)
7. [身份源对接接口](#7-身份源对接接口)
8. [策略热加载机制](#8-策略热加载机制)
9. [审计日志系统](#9-审计日志系统)
10. [安全设计](#10-安全设计)
11. [完整代码示例](#11-完整代码示例)
12. [部署要求](#12-部署要求)
13. [与现有插件的关系](#13-与现有插件的关系)
14. [开发计划](#14-开发计划)

---

## 1. 设计原则与技术选型

### 1.1 核心设计原则

| 原则 | 说明 |
|:-----|:-----|
| **不造轮子** | Casbin 已是事实标准（20K+ Star, Apache 2.0），直接用 |
| **插件最小化** | 权限引擎只做权限判断，不耦合业务逻辑 |
| **委婉拒绝** | 内部员工→正常返回；外部人员→委婉拒绝话术（安全红线） |
| **审计必达** | 每次权限判断必须写 AuditLog，不可跳过 |
| **热更新** | 修改策略文件/数据库后，Casbin 内存缓存即时刷新，无需重启 |

### 1.2 技术选型决策

| 组件 | 选择 | 理由 |
|:-----|:-----|:-----|
| **权限引擎** | Casbin Python (casbin) | Apache 2.0, RBAC+ABAC+RESTful 全支持, 社区活跃 |
| **ORM** | SQLAlchemy 2.x (async) | DDW 插件标准栈, asyncpg 适配 PostgreSQL |
| **Web 框架** | FastAPI + APIRouter | DDW 插件标准栈, 自动生成 OpenAPI |
| **数据库** | PostgreSQL 14+ | Casbin 有官方 `casbin-postgres-adapter`, 生产级 |
| **缓存** | casbin 内存缓存 + 可选 Redis | Casbin 自带内存缓存，高频查询 O(1) |

### 1.3 为什么不选其他方案

| 方案 | 否决原因 |
|:-----|:---------|
| **Casdoor** | Go 语言，DDW 是 Python 栈；Casdoor 是完整 IAM 系统，过于重量级 |
| **自建 RBAC** | 重复造轮子，无法覆盖 ABAC/RESTful 等复杂场景 |
| **Keycloak** | Java 生态，DDW 无 JVM 依赖 |
| **django-guardian** | 绑定 Django，与 FastAPI 不兼容 |

---

## 2. 插件架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                     DDW AI Hub 平台                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                  插件组合式部署                            │   │
│  │                                                          │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │   │
│  │  │ ddw-smart-cs │  │ ddw-erp-data │  │ ddw-cs-kb    │   │   │
│  │  │ (智能客服)    │  │ (ERP数据)    │  │ (知识库)     │   │   │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘   │   │
│  │         │                 │                  │            │   │
│  │         │   check_permission()               │            │   │
│  │         │   check_permission()               │            │   │
│  │         ▼                 ▼                  │            │   │
│  │  ┌────────────────────────────────────────┐  │            │   │
│  │  │     ddw-permission-engine              │  │            │   │
│  │  │     (权限引擎 — 本次设计)               │  │            │   │
│  │  │                                        │◄─┘            │   │
│  │  │  ┌─────────┐  ┌──────────┐  ┌───────┐ │              │   │
│  │  │  │ Casbin  │  │ User/Role│  │ Audit │ │              │   │
│  │  │  │ Engine  │  │ Service  │  │  Log  │ │              │   │
│  │  │  └─────────┘  └──────────┘  └───────┘ │              │   │
│  │  └────────────────┬───────────────────────┘              │   │
│  │                   │                                      │   │
│  │                   │  接收同步数据                         │   │
│  │                   ▼                                      │   │
│  │  ┌───────────────────────────────────────┐               │   │
│  │  │     身份源适配器 (adapter 插件)         │               │   │
│  │  │  ┌──────────┐ ┌──────────┐ ┌────────┐│               │   │
│  │  │  │ 钉钉     │ │ 飞书     │ │ 企微   ││               │   │
│  │  │  │ adapter  │ │ adapter  │ │ adapter││               │   │
│  │  │  └──────────┘ └──────────┘ └────────┘│               │   │
│  │  └───────────────────────────────────────┘               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────┐  ┌──────────────────────────────┐     │
│  │ PostgreSQL           │  │ Casbin Model/Policy Files    │     │
│  │ (users, roles,       │  │ (model.conf + policy.csv)    │     │
│  │  permissions,        │  │                              │     │
│  │  audit_log)          │  │                              │     │
│  └──────────────────────┘  └──────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 插件目录结构

```
ddw-permission-engine/
├── manifest.yaml              # 插件元数据
├── README.md                  # 插件文档
├── requirements.txt           # Python 依赖
├── __init__.py                # 包入口 + register()
├── models.py                  # SQLAlchemy ORM 模型
├── schemas.py                 # Pydantic 请求/响应模型
├── service.py                 # 核心业务逻辑（Casbin 封装）
├── router.py                  # FastAPI 路由端点
├── db.py                      # 数据库初始化
├── hot_reload.py              # 策略热加载模块
├── locales/                   # 委婉拒绝话术
│   ├── zh-CN.json
│   └── en.json
├── config/
│   ├── model.conf             # Casbin RBAC+ABAC 模型定义
│   ├── policy.csv             # 默认策略（空）
│   └── deny_message.json      # 拒绝话术模板
└── tests/
    ├── __init__.py
    ├── conftest.py            # 测试 Fixtures
    ├── test_permission.py     # 权限判断单元测试
    ├── test_casbin.py         # Casbin 引擎测试
    ├── test_api.py            # API 端点测试
    └── test_hot_reload.py     # 热加载测试
```

### 2.3 manifest.yaml

```yaml
name: ddw-permission-engine
version: 0.1.0
description: "基于 Casbin 的 RBAC+ABAC 权限引擎，所有业务插件的公共底座"
author: "DDW Team"
license: "Apache-2.0"
engine: ">=2.0.0"
isolation: inline

permissions:
  - "database:permission_engine"
  - network  # 访问外部身份源

config:
  required:
    - database_url
  optional:
    casbin_model_path: "config/model.conf"
    policy_auto_reload: true
    audit_log_retention_days: 90
    deny_message_default: "抱歉，该信息暂时无法为您查询，建议联系您的专属业务对接人。"

dependencies:
  plugins: {}
  python:
    - casbin>=1.36.0
    - casbin-postgres-adapter>=0.4.0
    - sqlalchemy>=2.0
    - asyncpg
    - pydantic>=2.0
    - pyyaml>=6.0
    - watchdog>=4.0

events:
  produces:
    - "permission.check_result"    # 权限判断结果事件
    - "permission.policy_changed"  # 策略变更事件
  consumes:
    - "identity.user_synced"       # 身份源同步用户
    - "identity.role_synced"       # 身份源同步角色
```

### 2.4 插件依赖关系

```
ddw-permission-engine (本插件，无外部插件依赖)
    ↑ 被以下插件依赖
    ├── ddw-smart-cs（智能客服）
    ├── ddw-erp-data（ERP 数据查询）
    ├── ddw-cs-knowledge（客服知识库）
    └── ddw-ent-knowledge（企业知识库同步）

ddw-permission-engine ← 接收以下适配器的同步数据
    ├── ddw-adapter-dingtalk
    ├── ddw-adapter-feishu
    └── ddw-adapter-wecom
```

---

## 3. Casbin 模型设计

### 3.1 RBAC + ABAC 混合模型（model.conf）

采用 Casbin 的 **RBAC with resource domains + ABAC attributes** 模型：

```ini
# model.conf — Casbin RBAC + ABAC 混合模型
# 适用于 DDW 多租户、多渠道权限场景

[request_definition]
r = sub, res, act

[policy_definition]
p = sub, res, act, eft

[role_definition]
g = _, _

[matchers]
m = g(r.sub, p.sub) && r.res == p.res && r.act == p.act

[policy_effect]
e = some(where (p.eft == allow)) && !some(where (p.eft == deny))
```

### 3.2 模型说明

| 组件 | 说明 |
|:-----|:-----|
| **request** | `sub`=用户ID, `res`=资源标识, `act`=操作(read/write/admin) |
| **policy** | `sub`=角色名, `res`=资源标识, `act`=操作, `eft`=allow/deny |
| **role_definition** | `g = _, _` — 支持用户→角色映射 (g, user, role) |
| **matchers** | 先检查角色继承(g)，再精确匹配资源和操作 |
| **policy_effect** | 优先级：deny > allow（显式拒绝优先） |

### 3.3 策略示例（policy.csv）

```csv
# 格式: p, 角色, 资源, 操作, 效果
# 内部员工基础权限
p, employee, customer:*, read, allow
p, employee, product:*, read, allow
p, employee, order:own, read, allow
p, employee, order:own, write, allow

# 客服人员权限
p, cs_agent, customer:*, read, allow
p, cs_agent, order:*, read, allow
p, cs_agent, knowledge:*, read, allow
p, cs_agent, erp:production:query, read, allow

# 部门主管权限
p, dept_manager, customer:dept, read, allow
p, dept_manager, order:dept, read, allow
p, dept_manager, order:dept, write, allow
p, dept_manager, report:dept, read, allow

# 管理员权限
p, admin, *, read, allow
p, admin, *, write, allow
p, admin, *, admin, allow

# 外部客户 — 显式拒绝业务数据访问
p, external_customer, erp:*, *, deny
p, external_customer, mes:*, *, deny
p, external_customer, crm:*, *, deny

# 供应商 — 仅允许查看自己的订单
p, supplier, order:own, read, allow

# 用户角色映射
g, user_001, employee
g, user_002, cs_agent
g, user_003, dept_manager
```

### 3.4 资源命名规范

```
{系统}:{模块}:{操作范围}

示例:
  erp:order:own        — ERP 订单（仅自己的）
  erp:order:dept       — ERP 订单（本部门的）
  erp:order:*          — ERP 订单（全部的）
  erp:production:query — ERP 生产查询
  customer:read        — 客户信息（读取）
  knowledge:read       — 知识库（读取）
  mes:production:query — MES 生产查询
```

---

## 4. 数据模型设计

### 4.1 ER 关系图

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│    User      │     │   UserRole   │     │    Role      │
│──────────────│     │──────────────│     │──────────────│
│ id (PK)      │◄───│ user_id (FK) │     │ id (PK)      │
│ external_id  │     │ role_id (FK) │────►│ name (UK)    │
│ channel      │     │ granted_at   │     │ parent_id(FK)│──┐
│ display_name │     │ granted_by   │     │ description  │  │
│ department   │     └──────────────┘     │ is_active    │  │
│ phone        │                          │ casbin_role  │  │
│ email        │     ┌──────────────┐     └──────────────┘  │
│ is_active    │     │RolePermission│           ▲            │
│ last_sync_at │     │──────────────│           │            │
│ created_at   │     │ role_id (FK) │───────────┘            │
│ updated_at   │     │ perm_group_id│                        │
└──────┬───────┘     │ resource     │     ┌──────────────┐   │
       │             │ action       │     │PermissionGroup│  │
       │             │ eft          │     │──────────────│   │
       │             │ granted_at   │     │ id (PK)      │   │
       │             └──────────────┘     │ name (UK)    │   │
       │                                  │ scope_type   │   │
       │             ┌──────────────┐     │ description  │   │
       └────────────►│  AuditLog    │     └──────────────┘   │
                     │──────────────│                        │
                     │ id (PK)      │                        │
                     │ user_id (FK) │                        │
                     │ resource     │                        │
                     │ action       │                        │
                     │ result       │                        │
                     │ reason       │                        │
                     │ ip_address   │                        │
                     │ created_at   │                        │
                     └──────────────┘                        │
                                                             │
                        ┌────────────────────────────────────┘
                        │ Role.parent_id 自引用（角色继承）
                        │ admin → dept_manager → employee
                        │ admin → cs_supervisor → cs_agent
                        └──────────────
```

### 4.2 User 表

```python
class User(Base):
    """用户表 — 支持多渠道身份统一管理"""
    __tablename__ = "permission_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 内部唯一标识（DDW 自己生成）
    internal_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # 外部系统用户ID（钉钉/飞书/企微的用户ID）
    external_id: Mapped[str | None] = mapped_column(String(128), index=True)
    # 来源渠道
    channel: Mapped[str] = mapped_column(String(32), index=True)
    # 'dingtalk' | 'feishu' | 'wecom' | 'web' | 'ldap' | 'manual'

    # 基本信息
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(256))
    department: Mapped[str | None] = mapped_column(String(128), index=True)
    title: Mapped[str | None] = mapped_column(String(128))

    # 用户类型（关键区分：内部员工 vs 外部客户/供应商）
    user_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="internal"
    )
    # 'internal' | 'external_customer' | 'supplier' | 'partner'

    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # 同步追踪
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_source: Mapped[str | None] = mapped_column(String(32))

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 关联
    roles: Mapped[list["Role"]] = relationship(
        "Role", secondary="permission_user_roles", back_populates="users"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="user")
```

### 4.3 Role 表

```python
class Role(Base):
    """角色表 — 支持角色继承（parent_id 自引用）"""
    __tablename__ = "permission_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Casbin 中的角色名，如 'admin', 'cs_agent', 'employee'
    casbin_role: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # 角色继承：parent_id 指向父角色
    # 例: cs_agent.parent_id → cs_supervisor
    #     cs_supervisor.parent_id → admin
    # 继承关系自动同步到 Casbin 的 g 策略
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("permission_roles.id"), index=True
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # 关联
    parent: Mapped["Role | None"] = relationship(
        "Role", remote_side="Role.id", back_populates="children"
    )
    children: Mapped[list["Role"]] = relationship("Role", back_populates="parent")
    users: Mapped[list["User"]] = relationship(
        "User", secondary="permission_user_roles", back_populates="roles"
    )
    permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="role"
    )
```

### 4.4 PermissionGroup 表

```python
class PermissionGroup(Base):
    """数据权限组 — 控制用户能看到哪些范围的数据"""
    __tablename__ = "permission_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # 'all' | 'department' | 'own' | 'custom'

    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # 数据范围:
    #   'all'        — 全部数据
    #   'department' — 本部门数据
    #   'own'        — 仅本人数据
    #   'custom'     — 自定义范围（JSON 配置）

    description: Mapped[str | None] = mapped_column(Text)
    # 自定义范围的 JSON 配置（scope_type='custom' 时使用）
    custom_config: Mapped[dict | None] = mapped_column(Text)
    # 示例: {"department_ids": ["dept_001", "dept_002"], "include_sub": true}

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # 关联
    role_permissions: Mapped[list["RolePermission"]] = relationship(
        "RolePermission", back_populates="permission_group"
    )
```

### 4.5 UserRole 关联表

```python
user_roles = Table(
    "permission_user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("permission_users.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("permission_roles.id"), primary_key=True),
    Column(
        "granted_at",
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    ),
    Column("granted_by", String(128), default="system"),
    # granted_by: 谁授权的（'system' = 自动同步，或管理员 user_id）
)
```

### 4.6 RolePermission 关联表

```python
class RolePermission(Base):
    """角色-权限 关联表"""
    __tablename__ = "role_permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("permission_roles.id"), index=True
    )
    permission_group_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("permission_groups.id")
    )
    # 资源标识，如 'erp:order:read', 'customer:*'
    resource: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    # 操作类型
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    # 'read' | 'write' | 'admin' | '*'
    # 效果
    eft: Mapped[str] = mapped_column(String(16), default="allow")
    # 'allow' | 'deny'

    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # 关联
    role: Mapped["Role"] = relationship("Role", back_populates="permissions")
    permission_group: Mapped["PermissionGroup | None"] = relationship(
        "PermissionGroup", back_populates="role_permissions"
    )
```

### 4.7 AuditLog 审计日志表

```python
class AuditLog(Base):
    """审计日志 — 记录每次权限判断（安全红线）"""
    __tablename__ = "permission_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 请求者
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str | None] = mapped_column(String(32))

    # 权限判断
    resource: Mapped[str] = mapped_column(String(256), index=True)
    action: Mapped[str] = mapped_column(String(32))
    result: Mapped[str] = mapped_column(String(16), index=True)
    # 'allowed' | 'denied'

    # 上下文
    reason: Mapped[str | None] = mapped_column(Text)
    # 拒绝原因: 'no_role' | 'no_permission' | 'explicit_deny' | 'inactive_user' | 'external_user'
    matched_policies: Mapped[str | None] = mapped_column(Text)
    # JSON 格式的匹配策略列表（调试用）
    deny_message: Mapped[str | None] = mapped_column(Text)
    # 返回给用户的委婉拒绝话术

    # 来源
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(256))
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    # 链路追踪ID

    # 调用来源插件
    source_plugin: Mapped[str | None] = mapped_column(String(64))

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    # 关联
    user: Mapped["User | None"] = relationship("User", back_populates="audit_logs")
```

### 4.8 数据库初始化

```python
"""db.py — 数据库引擎初始化"""
import os
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from models import Base

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
            "PERMISSION_ENGINE_DATABASE_URL",
            "postgresql+asyncpg://ddw:ddw@127.0.0.1:5432/permission_engine",
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
        raise RuntimeError("请先调用 init_db() 初始化数据库")
    return _session_maker
```

---

## 5. API 端点设计

### 5.1 端点清单

所有端点挂载在 `/api/v1/plugins/ddw-permission-engine/` 下：

| 方法 | 路径 | 说明 | 权限要求 |
|:-----|:-----|:-----|:---------|
| `GET` | `/health` | 健康检查 | 无 |
| **权限判断** | | | |
| `POST` | `/check` | 权限判断（核心接口） | 无 |
| `POST` | `/check/batch` | 批量权限判断 | 无 |
| `GET` | `/user/{user_id}/permissions` | 查询用户所有权限 | admin |
| **用户管理** | | | |
| `GET` | `/users` | 列出用户（分页） | admin |
| `POST` | `/users` | 创建用户 | admin |
| `GET` | `/users/{user_id}` | 查询用户详情 | admin |
| `PUT` | `/users/{user_id}` | 更新用户 | admin |
| `DELETE` | `/users/{user_id}` | 删除用户 | admin |
| `POST` | `/users/{user_id}/roles` | 分配角色 | admin |
| `DELETE` | `/users/{user_id}/roles/{role_id}` | 移除角色 | admin |
| **角色管理** | | | |
| `GET` | `/roles` | 列出所有角色 | admin |
| `POST` | `/roles` | 创建角色 | admin |
| `GET` | `/roles/{role_id}` | 角色详情 | admin |
| `PUT` | `/roles/{role_id}` | 更新角色 | admin |
| `DELETE` | `/roles/{role_id}` | 删除角色 | admin |
| `GET` | `/roles/{role_id}/permissions` | 角色的权限列表 | admin |
| `POST` | `/roles/{role_id}/permissions` | 给角色添加权限 | admin |
| `DELETE` | `/roles/{role_id}/permissions/{perm_id}` | 移除角色权限 | admin |
| **权限组管理** | | | |
| `GET` | `/permission-groups` | 列出权限组 | admin |
| `POST` | `/permission-groups` | 创建权限组 | admin |
| `PUT` | `/permission-groups/{group_id}` | 更新权限组 | admin |
| `DELETE` | `/permission-groups/{group_id}` | 删除权限组 | admin |
| **Casbin 策略管理** | | | |
| `GET` | `/policy/current` | 查看当前 Casbin 策略 | admin |
| `POST` | `/policy/sync` | 从数据库同步到 Casbin | admin |
| `POST` | `/policy/reload` | 强制重载策略文件 | admin |
| `GET` | `/policy/model` | 查看 Casbin 模型配置 | admin |
| `GET` | `/policy/stats` | 策略统计信息 | admin |
| **审计日志** | | | |
| `GET` | `/audit-logs` | 查询审计日志（分页） | admin |
| `GET` | `/audit-logs/stats` | 审计日志统计 | admin |
| `GET` | `/audit-logs/user/{user_id}` | 某用户的审计日志 | admin |

### 5.2 核心接口详解

#### 权限判断接口 `POST /check`

**请求体：**

```json
{
    "user_id": "user_001",
    "resource": "erp:order:read",
    "action": "read",
    "context": {
        "department_id": "dept_003",
        "ip_address": "192.168.1.100"
    }
}
```

**响应（允许）：**

```json
{
    "allowed": true,
    "user_id": "user_001",
    "resource": "erp:order:read",
    "action": "read",
    "matched_roles": ["employee", "cs_agent"],
    "matched_policies": [
        {"sub": "employee", "res": "erp:order:read", "act": "read", "eft": "allow"}
    ],
    "data_scope": "own",
    "request_id": "req_abc123"
}
```

**响应（拒绝）：**

```json
{
    "allowed": false,
    "user_id": "user_ext_001",
    "resource": "erp:order:read",
    "action": "read",
    "reason": "external_user",
    "deny_message": "抱歉，该信息暂时无法为您查询，建议联系您的专属业务对接人。",
    "request_id": "req_def456"
}
```

---

## 6. 业务插件集成方式

### 6.1 业务插件调用流程

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ 业务插件     │     │ 权限引擎     │     │ 审计日志     │
│ (smart-cs)  │     │ (permission) │     │ (AuditLog)   │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       │ 1. check_permission│                    │
       │   (user_id,        │                    │
       │    resource,       │                    │
       │    action)         │                    │
       │───────────────────►│                    │
       │                    │ 2. 查找用户        │
       │                    │    获取角色        │
       │                    │    Casbin Enforce  │
       │                    │                    │
       │                    │ 3. 写审计日志      │
       │                    │───────────────────►│
       │                    │                    │
       │ 4. 返回结果        │                    │
       │◄───────────────────│                    │
       │                    │                    │
       │ 5a. allowed → 正常执行业务逻辑           │
       │ 5b. denied  → 返回委婉拒绝话术          │
       │                    │                    │
```

### 6.2 业务插件代码示例

```python
"""ddw-smart-cs 中调用权限引擎的示例"""
import httpx
from fastapi import HTTPException


class SmartCSPlugin:
    """智能客服插件"""

    PERMISSION_ENGINE_URL = "http://localhost:8000/api/v1/plugins/ddw-permission-engine"

    async def handle_customer_query(
        self,
        user_id: str,
        query: str,
        channel: str,
    ) -> dict:
        """处理客户查询 — 带权限感知的业务逻辑"""

        # 第一步：判断用户是否有权查询 ERP 数据
        if self._is_erp_query(query):
            permission = await self._check_permission(
                user_id=user_id,
                resource="erp:production:query",
                action="read",
            )

            if not permission["allowed"]:
                # 安全红线：外部用户返回委婉拒绝
                return {
                    "type": "text",
                    "content": permission["deny_message"],
                    "meta": {"blocked_by": "permission_engine"},
                }

        # 第二步：有权限，正常执行查询
        result = await self._query_erp_data(query)
        return {"type": "text", "content": result}

    async def _check_permission(
        self, user_id: str, resource: str, action: str
    ) -> dict:
        """调用权限引擎"""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.PERMISSION_ENGINE_URL}/check",
                json={
                    "user_id": user_id,
                    "resource": resource,
                    "action": action,
                },
                timeout=2.0,  # 权限判断必须快，超时即拒绝
            )
            if resp.status_code != 200:
                # 权限引擎不可用时，默认拒绝（安全优先）
                return {
                    "allowed": False,
                    "deny_message": "系统维护中，请稍后再试。",
                    "reason": "engine_unavailable",
                }
            return resp.json()

    def _is_erp_query(self, query: str) -> bool:
        """判断查询是否涉及 ERP 数据"""
        erp_keywords = ["订单", "库存", "生产", "出货", "价格", "库存量"]
        return any(kw in query for kw in erp_keywords)
```

### 6.3 委婉拒绝话术模板

```json
{
    "default": "抱歉，该信息暂时无法为您查询，建议联系您的专属业务对接人。",
    "external_user": "您好，此功能暂未对您开放，如需帮助请联系客服热线。",
    "no_permission": "抱歉，您暂时没有查看此信息的权限，如有需要请联系您的主管。",
    "inactive_user": "您的账号当前未激活，请联系管理员处理。",
    "engine_unavailable": "系统维护中，请稍后再试。",
    "expired_session": "您的会话已过期，请重新登录。"
}
```

---

## 7. 身份源对接接口

### 7.1 对接架构

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ 钉钉适配器   │     │ 飞书适配器   │     │ 企微适配器   │
│ (adapter)    │     │ (adapter)    │     │ (adapter)    │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       │ POST /identity/sync│                    │
       │ POST /identity/sync│                    │
       │ POST /identity/sync│                    │
       │───────────────────►│                    │
       │                    │───────────────────►│
       │                    │                    │
       │                    ▼                    │
       │         ┌──────────────────┐            │
       │         │ 权限引擎          │            │
       │         │ /identity/sync   │            │
       │         │                  │            │
       │         │ 1. Upsert 用户   │            │
       │         │ 2. Upsert 角色   │            │
       │         │ 3. 映射到 Casbin  │            │
       │         │ 4. 发布事件      │            │
       │         └──────────────────┘            │
```

### 7.2 身份同步 API

#### `POST /identity/sync`

**请求体（用户同步）：**

```json
{
    "type": "users",
    "channel": "dingtalk",
    "data": [
        {
            "external_id": "01234567890",
            "name": "张三",
            "email": "zhangsan@company.com",
            "phone": "13800138000",
            "department": "客服部",
            "title": "高级客服",
            "roles": ["cs_agent", "employee"],
            "status": "active",
            "channel": "dingtalk"
        }
    ]
}
```

**请求体（角色同步）：**

```json
{
    "type": "roles",
    "channel": "dingtalk",
    "data": [
        {
            "external_id": "role_001",
            "name": "客服专员",
            "description": "DDW 平台客服专员角色",
            "permissions": ["customer:read", "order:read", "knowledge:read"]
        }
    ]
}
```

**请求体（部门同步）：**

```json
{
    "type": "departments",
    "channel": "dingtalk",
    "data": [
        {
            "external_id": "dept_001",
            "name": "客服部",
            "parent_id": null,
            "leader": "user_001"
        }
    ]
}
```

### 7.3 身份同步服务代码

```python
"""service.py 中的身份同步逻辑"""

async def sync_users_from_adapter(
    channel: str,
    users_data: list[dict],
    db: AsyncSession,
) -> dict:
    """接收适配器同步的用户数据，Upsert 到本地数据库"""

    synced = 0
    created = 0
    updated = 0

    for user_data in users_data:
        # 查找已有用户
        stmt = select(User).where(
            User.external_id == user_data["external_id"],
            User.channel == channel,
        )
        existing = (await db.execute(stmt)).scalar_one_or_none()

        if existing:
            # 更新已有用户
            existing.display_name = user_data["name"]
            existing.email = user_data.get("email")
            existing.phone = user_data.get("phone")
            existing.department = user_data.get("department")
            existing.title = user_data.get("title")
            existing.is_active = user_data.get("status") == "active"
            existing.last_sync_at = datetime.now(timezone.utc)
            updated += 1
        else:
            # 创建新用户
            new_user = User(
                internal_id=f"{channel}_{user_data['external_id']}",
                external_id=user_data["external_id"],
                channel=channel,
                display_name=user_data["name"],
                email=user_data.get("email"),
                phone=user_data.get("phone"),
                department=user_data.get("department"),
                title=user_data.get("title"),
                user_type=_infer_user_type(user_data),
                is_active=user_data.get("status") == "active",
                last_sync_at=datetime.now(timezone.utc),
                sync_source=channel,
            )
            db.add(new_user)
            created += 1

        synced += 1

    await db.commit()

    # 同步完成后，触发 Casbin 策略重载
    await _reload_casbin_from_db()

    return {
        "synced": synced,
        "created": created,
        "updated": updated,
        "channel": channel,
    }


def _infer_user_type(user_data: dict) -> str:
    """根据数据推断用户类型"""
    if user_data.get("channel") in ("dingtalk", "feishu", "wecom", "ldap"):
        return "internal"
    if user_data.get("roles"):
        for role in user_data["roles"]:
            if "external" in role or "customer" in role or "supplier" in role:
                return "external_customer" if "customer" in role else "supplier"
    return "internal"
```

---

## 8. 策略热加载机制

### 8.1 三种触发方式

| 触发方式 | 说明 | 适用场景 |
|:---------|:-----|:---------|
| **API 触发** | `POST /policy/sync` | 管理员在后台修改权限后点击同步 |
| **数据库变更** | SQLAlchemy event 监听 | RolePermission 表发生 INSERT/UPDATE/DELETE |
| **文件监听** | watchdog 监听 config/ 目录 | 开发/测试环境直接修改 policy.csv |

### 8.2 热加载流程

```
策略变更触发
    │
    ├─ API: POST /policy/sync
    ├─ DB:  RolePermission INSERT/UPDATE/DELETE
    └─ File: policy.csv 被修改
    │
    ▼
┌──────────────────────────┐
│ 1. 计算新策略的 hash     │
│ 2. 对比当前缓存的 hash   │
│ 3. 相同 → 跳过           │
│ 4. 不同 → 执行重载       │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 5. 从数据库重建 Casbin   │
│    策略（RBAC 角色映射   │
│    + 权限策略）          │
│ 6. 调用 e.load_policy()  │
│ 7. 更新缓存 hash         │
│ 8. 发布事件              │
│    permission.policy_changed│
│ 9. 记录审计日志          │
└──────────────────────────┘
```

### 8.3 热加载代码

```python
"""hot_reload.py — 策略热加载模块"""
import asyncio
import hashlib
import json
import logging
from typing import Optional

import casbin
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User, Role, RolePermission, user_roles

logger = logging.getLogger(__name__)

# Casbin Enforcer 单例
_enforcer: Optional[casbin.Enforcer] = None
_policy_hash: Optional[str] = None


async def get_enforcer() -> casbin.Enforcer:
    """获取 Casbin Enforcer 单例"""
    global _enforcer
    if _enforcer is None:
        _enforcer = casbin.Enforcer(
            "config/model.conf",  # 模型文件
        )
        await _reload_from_db()
    return _enforcer


async def _reload_from_db(db: AsyncSession | None = None):
    """从数据库重建 Casbin 策略"""
    global _policy_hash

    from db import session_maker

    if db is None:
        async with session_maker()() as db:
            await _do_reload(db)
    else:
        await _do_reload(db)


async def _do_reload(db: AsyncSession):
    """执行实际的策略重载"""
    global _policy_hash, _enforcer

    # 1. 清除旧策略
    _enforcer.clear_policy()

    # 2. 加载角色继承关系（Role.parent_id）
    await _load_role_hierarchy(db)

    # 3. 加载用户角色映射
    await _load_user_role_mapping(db)

    # 4. 加载权限策略
    await _load_permission_policies(db)

    # 5. 计算新 hash
    policy_str = json.dumps(
        sorted([list(p) for p in _enforcer.get_policy()]), sort_keys=True
    )
    new_hash = hashlib.md5(policy_str.encode()).hexdigest()

    if new_hash != _policy_hash:
        _policy_hash = new_hash
        logger.info("Casbin 策略已重载，hash=%s", new_hash[:8])
    else:
        logger.debug("策略无变化，跳过重载")


async def _load_role_hierarchy(db: AsyncSession):
    """加载角色继承关系到 Casbin g 策略"""
    stmt = select(Role).where(Role.is_active == True, Role.parent_id.isnot(None))
    roles = (await db.execute(stmt)).scalars().all()

    for role in roles:
        parent_stmt = select(Role).where(Role.id == role.parent_id)
        parent = (await db.execute(parent_stmt)).scalar_one_or_none()
        if parent:
            _enforcer.add_policy(role.casbin_role, "*", "*", "allow")
            # 角色继承: 子角色 → 父角色
            # 在 Casbin 中通过 g 策略实现
            # 这里用 policy 模拟: 子角色继承父角色的所有权限
            _enforcer.add_grouping_policy(role.casbin_role, parent.casbin_role)


async def _load_user_role_mapping(db: AsyncSession):
    """加载用户角色映射到 Casbin"""
    stmt = select(User).where(User.is_active == True)
    users = (await db.execute(stmt)).scalars().all()

    for user in users:
        for role in user.roles:
            if role.is_active:
                _enforcer.add_grouping_policy(user.internal_id, role.casbin_role)


async def _load_permission_policies(db: AsyncSession):
    """加载权限策略"""
    stmt = select(RolePermission)
    perms = (await db.execute(stmt)).scalars().all()

    for perm in perms:
        # 获取角色的 casbin_role
        role_stmt = select(Role).where(Role.id == perm.role_id)
        role = (await db.execute(role_stmt)).scalar_one_or_none()
        if role and role.is_active:
            _enforcer.add_policy(
                role.casbin_role,
                perm.resource,
                perm.action,
                perm.eft,
            )


async def check_permission(
    user_id: str,
    resource: str,
    action: str,
) -> dict:
    """
    核心权限判断方法 — 所有业务插件通过此方法判断权限

    Returns:
        {
            "allowed": bool,
            "reason": str | None,
            "matched_roles": list[str],
            "deny_message": str | None,
        }
    """
    from db import session_maker
    from locales import get_deny_message

    enforcer = await get_enforcer()

    async with session_maker()() as db:
        # 1. 查找用户
        user_stmt = select(User).where(User.internal_id == user_id)
        user = (await db.execute(user_stmt)).scalar_one_or_none()

        if user is None:
            return {
                "allowed": False,
                "reason": "user_not_found",
                "matched_roles": [],
                "deny_message": get_deny_message("user_not_found"),
            }

        if not user.is_active:
            return {
                "allowed": False,
                "reason": "inactive_user",
                "matched_roles": [],
                "deny_message": get_deny_message("inactive_user"),
            }

        # 2. 外部用户特殊处理（安全红线）
        if user.user_type in ("external_customer", "supplier", "partner"):
            # 外部用户只能访问显式授权的资源
            result = enforcer.enforce(user.internal_id, resource, action)
            if not result:
                return {
                    "allowed": False,
                    "reason": "external_user",
                    "matched_roles": [r.name for r in user.roles],
                    "deny_message": get_deny_message("external_user"),
                }

        # 3. Casbin 权限判断
        result = enforcer.enforce(user.internal_id, resource, action)

        # 4. 获取匹配的角色
        matched_roles = []
        for role in user.roles:
            if enforcer.has_role_for_user(user.internal_id, role.casbin_role):
                matched_roles.append(role.casbin_role)

        # 5. 写审计日志
        await _write_audit_log(
            db=db,
            user_id=user.internal_id,
            channel=user.channel,
            resource=resource,
            action=action,
            result="allowed" if result else "denied",
            matched_roles=matched_roles,
        )

        if result:
            return {
                "allowed": True,
                "reason": None,
                "matched_roles": matched_roles,
                "deny_message": None,
            }
        else:
            return {
                "allowed": False,
                "reason": "no_permission",
                "matched_roles": matched_roles,
                "deny_message": get_deny_message("no_permission"),
            }
```

---

## 9. 审计日志系统

### 9.1 审计日志设计原则

| 原则 | 说明 |
|:-----|:-----|
| **必达** | 每次权限判断必须写审计日志，不可跳过 |
| **异步写入** | 审计日志写入不阻塞权限判断（先判断，后异步写日志） |
| **保留期** | 默认 90 天，可通过配置调整 |
| **查询友好** | 支持按用户/资源/时间范围/结果类型查询 |
| **不可篡改** | 审计日志表只有 INSERT 和 SELECT，没有 UPDATE/DELETE |

### 9.2 审计日志查询接口

```python
@router.get("/audit-logs", response_model=list[AuditLogOut])
async def query_audit_logs(
    user_id: str | None = None,
    resource: str | None = None,
    result: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(_get_session),
):
    """查询审计日志"""
    stmt = select(AuditLog)

    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if resource:
        stmt = stmt.where(AuditLog.resource.like(f"%{resource}%"))
    if result:
        stmt = stmt.where(AuditLog.result == result)
    if start_time:
        stmt = stmt.where(AuditLog.created_at >= start_time)
    if end_time:
        stmt = stmt.where(AuditLog.created_at <= end_time)

    stmt = stmt.order_by(AuditLog.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    rows = (await db.execute(stmt)).scalars().all()
    return [AuditLogOut.model_validate(r) for r in rows]
```

### 9.3 审计日志统计

```python
@router.get("/audit-logs/stats")
async def audit_log_stats(
    days: int = Query(default=7, ge=1, le=365),
    db: AsyncSession = Depends(_get_session),
):
    """审计日志统计"""
    from sqlalchemy import func

    since = datetime.now(timezone.utc) - timedelta(days=days)

    # 总请求数
    total_stmt = select(func.count(AuditLog.id)).where(
        AuditLog.created_at >= since
    )
    total = (await db.execute(total_stmt)).scalar() or 0

    # 允许/拒绝数
    allowed_stmt = select(func.count(AuditLog.id)).where(
        AuditLog.created_at >= since, AuditLog.result == "allowed"
    )
    allowed = (await db.execute(allowed_stmt)).scalar() or 0

    denied_stmt = select(func.count(AuditLog.id)).where(
        AuditLog.created_at >= since, AuditLog.result == "denied"
    )
    denied = (await db.execute(denied_stmt)).scalar() or 0

    # Top 拒绝原因
    deny_reason_stmt = (
        select(AuditLog.reason, func.count(AuditLog.id).label("count"))
        .where(AuditLog.created_at >= since, AuditLog.result == "denied")
        .group_by(AuditLog.reason)
        .order_by(func.count(AuditLog.id).desc())
        .limit(10)
    )
    deny_reasons = (await db.execute(deny_reason_stmt)).all()

    return {
        "period_days": days,
        "total_checks": total,
        "allowed": allowed,
        "denied": denied,
        "allow_rate": round(allowed / max(total, 1) * 100, 2),
        "top_deny_reasons": [
            {"reason": r.reason, "count": r.count} for r in deny_reasons
        ],
    }
```

---

## 10. 安全设计

### 10.1 安全红线清单

| # | 红线 | 实现方式 |
|:--|:-----|:---------|
| 1 | 外部用户不能查询 ERP/MES/CRM 数据 | `user_type` 检查 + Casbin `deny` 策略 |
| 2 | 拒绝时不暴露"有数据但没权限" | 返回委婉话术，不返回具体原因 |
| 3 | 审计日志不可篡改 | AuditLog 表只有 INSERT/SELECT |
| 4 | 权限引擎不可用时默认拒绝 | `_check_permission` 异常处理返回 denied |
| 5 | 权限判断必须快速 | Casbin 内存缓存 O(1)，超时 2s 默认拒绝 |
| 6 | 策略变更必须记录 | 每次重载都发布 `permission.policy_changed` 事件 |

### 10.2 拒绝话术安全原则

```
✅ 正确话术:
  "抱歉，该信息暂时无法为您查询，建议联系您的专属业务对接人。"
  "此功能暂未对您开放，如需帮助请联系客服热线。"
  "您暂时没有查看此信息的权限，如有需要请联系您的主管。"

❌ 禁止话术（暴露系统信息）:
  "您没有 ERP:order:read 权限"  ← 泄露资源路径
  "您不是内部员工"  ← 泄露身份分类
  "需要 cs_agent 角色"  ← 泄露角色体系
  "Casbin 策略拒绝"  ← 泄露技术实现
```

---

## 11. 完整代码示例

### 11.1 插件入口 `__init__.py`

```python
"""ddw-permission-engine — 基于 Casbin 的 RBAC+ABAC 权限引擎"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI

logger = logging.getLogger(__name__)
PLUGIN_NAME = "ddw-permission-engine"
PLUGIN_PREFIX = f"/api/v1/plugins/{PLUGIN_NAME}"
PLUGIN_VERSION = "0.1.0"


def register(app: FastAPI, config: dict[str, Any] | None = None) -> None:
    """平台挂载入口"""
    import asyncio
    from db import init_db
    from router import router
    from hot_reload import get_enforcer

    cfg = config or {}
    db_url = cfg.get(
        "database_url",
        "postgresql+asyncpg://ddw:ddw@127.0.0.1:5432/permission_engine",
    )

    # 初始化数据库
    asyncio.get_event_loop().run_until_complete(
        init_db(database_url=db_url)
    )

    # 初始化 Casbin Enforcer
    asyncio.get_event_loop().run_until_complete(
        get_enforcer()
    )

    # 挂载路由
    app.include_router(router, prefix=PLUGIN_PREFIX, tags=[PLUGIN_NAME])
    logger.info(
        "%s v%s registered (api=%s)", PLUGIN_NAME, PLUGIN_VERSION, PLUGIN_PREFIX
    )
```

### 11.2 路由模块 `router.py`

```python
"""router.py — API 路由端点"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db import session_maker
from hot_reload import check_permission as _check_permission
from hot_reload import get_enforcer, _reload_from_db
from models import AuditLog, PermissionGroup, Role, RolePermission, User, user_roles

router = APIRouter()


# ── Pydantic 模型 ──────────────────────────────────────────────

class PermissionCheckIn(BaseModel):
    user_id: str = Field(..., description="用户内部ID")
    resource: str = Field(..., description="资源标识")
    action: str = Field(..., description="操作类型")
    context: dict[str, Any] | None = Field(None, description="上下文（部门/IP等）")


class PermissionCheckOut(BaseModel):
    allowed: bool
    user_id: str
    resource: str
    action: str
    reason: str | None = None
    matched_roles: list[str] = []
    deny_message: str | None = None
    request_id: str


class UserIn(BaseModel):
    external_id: str | None = None
    channel: str = "manual"
    display_name: str
    phone: str | None = None
    email: str | None = None
    department: str | None = None
    title: str | None = None
    user_type: str = "internal"


class UserOut(BaseModel):
    id: int
    internal_id: str
    external_id: str | None
    channel: str
    display_name: str
    department: str | None
    user_type: str
    is_active: bool
    created_at: datetime


class RoleIn(BaseModel):
    name: str
    casbin_role: str
    description: str | None = None
    parent_id: int | None = None


class RoleOut(BaseModel):
    id: int
    name: str
    casbin_role: str
    description: str | None
    parent_id: int | None
    is_active: bool


class PermissionGroupIn(BaseModel):
    name: str
    scope_type: str
    description: str | None = None


class IdentitySyncIn(BaseModel):
    type: str  # 'users' | 'roles' | 'departments'
    channel: str
    data: list[dict[str, Any]]


class AuditLogOut(BaseModel):
    id: int
    user_id: str
    resource: str
    action: str
    result: str
    reason: str | None
    deny_message: str | None
    source_plugin: str | None
    created_at: datetime


# ── 健康检查 ──────────────────────────────────────────────────

@router.get("/health")
async def health() -> dict[str, Any]:
    return {
        "plugin": PLUGIN_NAME,
        "status": "ok",
        "version": PLUGIN_VERSION,
        "casbin_engine": "loaded",
    }


# ── 核心：权限判断 ────────────────────────────────────────────

@router.post("/check", response_model=PermissionCheckOut)
async def check_permission(
    payload: PermissionCheckIn,
    request: Request,
):
    """权限判断核心接口"""
    request_id = str(uuid.uuid4())[:8]

    result = await _check_permission(
        user_id=payload.user_id,
        resource=payload.resource,
        action=payload.action,
    )

    return PermissionCheckOut(
        allowed=result["allowed"],
        user_id=payload.user_id,
        resource=payload.resource,
        action=payload.action,
        reason=result.get("reason"),
        matched_roles=result.get("matched_roles", []),
        deny_message=result.get("deny_message"),
        request_id=request_id,
    )


@router.post("/check/batch")
async def check_permission_batch(
    checks: list[PermissionCheckIn],
):
    """批量权限判断"""
    results = []
    for check in checks:
        result = await _check_permission(
            user_id=check.user_id,
            resource=check.resource,
            action=check.action,
        )
        results.append({
            "user_id": check.user_id,
            "resource": check.resource,
            "action": check.action,
            **result,
        })
    return results


# ── 身份源对接 ────────────────────────────────────────────────

@router.post("/identity/sync")
async def identity_sync(
    payload: IdentitySyncIn,
    db: AsyncSession = Depends(_get_session),
):
    """接收适配器插件同步的用户/角色/部门数据"""
    if payload.type == "users":
        from service import sync_users_from_adapter
        result = await sync_users_from_adapter(
            channel=payload.channel,
            users_data=payload.data,
            db=db,
        )
        return result
    elif payload.type == "roles":
        from service import sync_roles_from_adapter
        result = await sync_roles_from_adapter(
            channel=payload.channel,
            roles_data=payload.data,
            db=db,
        )
        return result
    else:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的同步类型: {payload.type}"
        )


# ── 用户 CRUD ─────────────────────────────────────────────────

@router.get("/users", response_model=list[UserOut])
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    channel: str | None = None,
    is_active: bool | None = None,
    db: AsyncSession = Depends(_get_session),
):
    stmt = select(User)
    if channel:
        stmt = stmt.where(User.channel == channel)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()
    return [UserOut.model_validate(r) for r in rows]


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    payload: UserIn,
    db: AsyncSession = Depends(_get_session),
):
    import hashlib
    new_user = User(
        internal_id=f"manual_{hashlib.md5(payload.display_name.encode()).hexdigest()[:8]}",
        external_id=payload.external_id,
        channel=payload.channel,
        display_name=payload.display_name,
        phone=payload.phone,
        email=payload.email,
        department=payload.department,
        title=payload.title,
        user_type=payload.user_type,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return UserOut.model_validate(new_user)


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(_get_session),
):
    stmt = select(User).where(User.internal_id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return UserOut.model_validate(user)


# ── 角色 CRUD ─────────────────────────────────────────────────

@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    db: AsyncSession = Depends(_get_session),
):
    stmt = select(Role).where(Role.is_active == True)
    rows = (await db.execute(stmt)).scalars().all()
    return [RoleOut.model_validate(r) for r in rows]


@router.post("/roles", response_model=RoleOut, status_code=201)
async def create_role(
    payload: RoleIn,
    db: AsyncSession = Depends(_get_session),
):
    new_role = Role(
        name=payload.name,
        casbin_role=payload.casbin_role,
        description=payload.description,
        parent_id=payload.parent_id,
    )
    db.add(new_role)
    await db.commit()
    await db.refresh(new_role)

    # 重载 Casbin 策略
    await _reload_from_db(db)
    return RoleOut.model_validate(new_role)


# ── Casbin 策略管理 ───────────────────────────────────────────

@router.post("/policy/sync")
async def sync_policy(
    db: AsyncSession = Depends(_get_session),
):
    """从数据库同步策略到 Casbin"""
    await _reload_from_db(db)
    return {"status": "synced", "message": "策略已从数据库同步到 Casbin"}


@router.post("/policy/reload")
async def reload_policy_file():
    """强制重载策略文件"""
    from hot_reload import _reload_from_db
    await _reload_from_db()
    return {"status": "reloaded"}


@router.get("/policy/current")
async def get_current_policy():
    """查看当前 Casbin 策略"""
    enforcer = await get_enforcer()
    return {
        "policies": [list(p) for p in enforcer.get_policy()],
        "grouping_policies": [list(g) for g in enforcer.get_grouping_policy()],
    }


@router.get("/policy/stats")
async def policy_stats():
    """策略统计"""
    enforcer = await get_enforcer()
    return {
        "total_policies": len(enforcer.get_policy()),
        "total_grouping_policies": len(enforcer.get_grouping_policy()),
        "policy_hash": _policy_hash,
    }


# ── 审计日志 ──────────────────────────────────────────────────

@router.get("/audit-logs", response_model=list[AuditLogOut])
async def query_audit_logs(
    user_id: str | None = None,
    resource: str | None = None,
    result: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(_get_session),
):
    stmt = select(AuditLog)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if resource:
        stmt = stmt.where(AuditLog.resource.like(f"%{resource}%"))
    if result:
        stmt = stmt.where(AuditLog.result == result)
    stmt = stmt.order_by(AuditLog.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()
    return [AuditLogOut.model_validate(r) for r in rows]


# ── 数据库 Session 依赖 ──────────────────────────────────────

async def _get_session():
    async with session_maker()() as s:
        yield s
```

### 11.3 requirements.txt

```
casbin>=1.36.0
sqlalchemy>=2.0
asyncpg>=0.29.0
pydantic>=2.0
pyyaml>=6.0
httpx>=0.25.0
fastapi>=0.100.0
```

---

## 12. 部署要求

### 12.1 环境要求

| 组件 | 最低版本 | 推荐版本 | 说明 |
|:-----|:---------|:---------|:-----|
| Python | 3.11 | 3.12 | DDW 平台标准 |
| PostgreSQL | 14 | 16 | Casbin adapter 支持 |
| casbin | 1.36 | 最新 | RBAC+ABAC 核心 |
| SQLAlchemy | 2.0 | 最新 | ORM |
| FastAPI | 0.100 | 最新 | API 框架 |

### 12.2 环境变量

```bash
# 数据库
PERMISSION_ENGINE_DATABASE_URL=postgresql+asyncpg://ddw:ddw@127.0.0.1:5432/permission_engine

# Casbin
CASBIN_MODEL_PATH=config/model.conf
POLICY_AUTO_RELOAD=true

# 审计
AUDIT_LOG_RETENTION_DAYS=90

# 安全
DENY_MESSAGE_DEFAULT="抱歉，该信息暂时无法为您查询，建议联系您的专属业务对接人。"
```

### 12.3 Docker 部署

```yaml
# docker-compose.yml
version: '3.8'
services:
  permission-engine:
    build: .
    environment:
      - PERMISSION_ENGINE_DATABASE_URL=postgresql+asyncpg://ddw:ddw@db:5432/permission_engine
      - POLICY_AUTO_RELOAD=true
    depends_on:
      - db
    ports:
      - "8000:8000"

  db:
    image: postgres:16-alpine
    environment:
      - POSTGRES_DB=permission_engine
      - POSTGRES_USER=ddw
      - POSTGRES_PASSWORD=ddw
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

volumes:
  pgdata:
```

### 12.4 性能指标

| 指标 | 目标值 | 说明 |
|:-----|:-------|:-----|
| 权限判断延迟 | < 5ms | Casbin 内存缓存 O(1) |
| 策略热加载 | < 100ms | 从 DB 重建策略 |
| 并发权限判断 | 1000+ QPS | 无锁内存读 |
| 审计日志写入 | 异步，不阻塞判断 | 先判断后写日志 |
| 策略规模上限 | 100K 条策略 | Casbin 内存限制 |

---

## 13. 与现有插件的关系

### 13.1 在插件生态中的位置

```
                    ┌─────────────────────┐
                    │    DDW AI Hub       │
                    │    插件管理器        │
                    └─────────┬───────────┘
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                 │
   ┌────────▼────────┐ ┌─────▼──────┐ ┌───────▼───────┐
   │  身份源适配器    │ │ 业务插件   │ │  基础设施插件  │
   │  (adapter)      │ │ (business) │ │  (infra)      │
   └────────┬────────┘ └─────┬──────┘ └───────┬───────┘
            │                 │                 │
            │  sync_users()   │ check_permission()│
            │  sync_roles()   │                   │
            │                 │                   │
            └────────────────►│◄──────────────────┘
                              │
                    ┌─────────▼───────────┐
                    │ ddw-permission-engine│
                    │   (权限引擎 - 本插件) │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │    PostgreSQL       │
                    │  + Casbin Memory    │
                    └─────────────────────┘
```

### 13.2 与其他插件的交互矩阵

| 本插件 | 对方插件 | 交互方式 | 说明 |
|:-------|:---------|:---------|:-----|
| permission-engine | ddw-adapter-dingtalk | 接收身份同步 | 适配器调用 `/identity/sync` |
| permission-engine | ddw-adapter-feishu | 接收身份同步 | 适配器调用 `/identity/sync` |
| permission-engine | ddw-adapter-wecom | 接收身份同步 | 适配器调用 `/identity/sync` |
| permission-engine | ddw-smart-cs | 提供权限判断 | 智能客服调用 `/check` |
| permission-engine | ddw-erp-data | 提供权限判断 | ERP 数据查询调用 `/check` |
| permission-engine | ddw-cs-knowledge | 提供权限判断 | 知识库调用 `/check` |
| permission-engine | ddw-token-manager | 无直接交互 | 各自独立运行 |

---

## 14. 开发计划

### 14.1 分阶段交付

| 阶段 | 内容 | 工期 | 产出 |
|:-----|:-----|:-----|:-----|
| **P0: 核心** | 数据模型 + Casbin 引擎 + check_permission API | 3 天 | 可用的权限判断能力 |
| **P1: 管理** | 用户/角色 CRUD API + 身份同步接口 | 2 天 | 完整的管理后台 API |
| **P2: 热加载** | 策略热加载 + watchdog 监听 | 1 天 | 修改策略不重启 |
| **P3: 审计** | 审计日志 + 统计查询 | 1 天 | 安全合规 |
| **P4: 集成** | 与 smart-cs 和 adapter 的联调测试 | 2 天 | 端到端可验证 |

**总计：约 9 个工作日**

### 14.2 交付检查清单

- [ ] Casbin RBAC+ABAC 模型配置完成
- [ ] 6 张数据表 ORM 模型完成
- [ ] `POST /check` 权限判断接口可用
- [ ] 委婉拒绝话术机制生效
- [ ] 用户/角色 CRUD API 完成
- [ ] 身份源同步接口完成（对接 adapter）
- [ ] 策略热加载（API + DB + File 三种触发）
- [ ] 审计日志写入 + 查询接口
- [ ] 单元测试覆盖率 ≥ 80%
- [ ] manifest.yaml 声明完成

---

> **文档版本**：v1.0 | **最后更新**：2026-07-13 | **维护者**：DDW AI Hub Team
