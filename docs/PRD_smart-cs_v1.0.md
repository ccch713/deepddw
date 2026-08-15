# PRD: DDW Smart Customer Service Plugin v1.0

> 日期：2026-07-13
> 作者：MiMo V2.5 Pro（功能PRD）+ 架构审计（基于 Phase 2-3 调研）
> 状态：正式版

---

## 1. 产品概述

### 1.1 定位
DDW 智能客服插件是 DDW AI Hub 的企业级客服解决方案，基于插件组合式架构，支持多渠道统一接入、AI 自动回复、知识库检索、权限感知的业务数据查询。

### 1.2 V1 范围
- 权限引擎（Casbin RBAC + ABAC）
- 客服核心逻辑（消息接收→处理→回复）
- 多渠道身份识别（钉钉/飞书/企微/网站）
- 知识库问答（RAG 模式）
- 委婉拒绝（无权限用户）
- 审计日志

### 1.3 不在 V1 范围
- ERP/MES/SRM/OA 适配器（V1.5+）
- 工单系统（V2）
- 坐席管理（V2）

---

## 2. 用户故事

| ID | 用户故事 | 验收标准 |
|:--:|:---------|:---------|
| US-01 | 作为企业 IT 管理员，我希望在 DDW 后台配置用户角色和权限 | 可通过 API 创建用户/角色/权限组 |
| US-02 | 作为企业员工，我希望通过钉钉/飞书/企微向 AI 客服提问 | 三个渠道均可接收消息并回复 |
| US-03 | 作为外部客户，我希望通过网站向 AI 客服提问 | 网站渠道可接收消息并回复 |
| US-04 | 作为无权限用户，当我询问业务数据时，我希望得到委婉拒绝 | 返回"建议联系专属业务对接人" |
| US-05 | 作为有权限员工，当我查询 ERP 数据时，我希望得到正确结果 | 权限检查通过后返回数据 |
| US-06 | 作为管理员，我希望查看所有权限判断的审计日志 | 可查询审计日志 |

---

## 3. API 端点设计

### 3.1 权限管理

| 方法 | 路径 | 说明 |
|:-----|:-----|:-----|
| POST | /api/v1/permission/check | 权限判断 |
| POST | /api/v1/users | 创建用户 |
| GET | /api/v1/users | 用户列表 |
| POST | /api/v1/roles | 创建角色 |
| GET | /api/v1/roles | 角色列表 |
| POST | /api/v1/permission-groups | 创建权限组 |
| GET | /api/v1/permission-groups | 权限组列表 |
| POST | /api/v1/audit-logs/query | 查询审计日志 |

### 3.2 客服服务

| 方法 | 路径 | 说明 |
|:-----|:-----|:-----|
| POST | /api/v1/cs/message | 接收消息并回复 |
| POST | /api/v1/cs/knowledge/query | 知识库查询 |
| GET | /api/v1/cs/health | 健康检查 |

### 3.3 身份同步

| 方法 | 路径 | 说明 |
|:-----|:-----|:-----|
| POST | /api/v1/identity/sync | 适配器推送用户/角色数据 |

---

## 4. 数据模型

### User 表
| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| id | INTEGER PK | 主键 |
| external_id | VARCHAR(128) UNIQUE | 外部系统用户ID |
| name | VARCHAR(128) | 姓名 |
| channel | VARCHAR(32) | 来源渠道(dingtalk/feishu/wecom/website) |
| department | VARCHAR(128) | 部门 |
| status | VARCHAR(16) | active/inactive |
| created_at | DATETIME | 创建时间 |

### Role 表
| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| id | INTEGER PK | 主键 |
| name | VARCHAR(64) UNIQUE | 角色名 |
| description | VARCHAR(256) | 描述 |
| parent_id | INTEGER FK | 父角色ID(继承) |

### PermissionGroup 表
| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| id | INTEGER PK | 主键 |
| name | VARCHAR(64) UNIQUE | 权限组名 |
| data_scope | VARCHAR(32) | all/department/self/custom |
| allowed_resources | TEXT(JSON) | 允许的资源列表 |
| denied_resources | TEXT(JSON) | 拒绝的资源列表 |

### UserRole 关联表
| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| user_id | INTEGER FK | 用户ID |
| role_id | INTEGER FK | 角色ID |

### RolePermission 关联表
| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| role_id | INTEGER FK | 角色ID |
| permission_group_id | INTEGER FK | 权限组ID |

### AuditLog 表
| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| id | INTEGER PK | 主键 |
| user_id | INTEGER | 用户ID |
| channel | VARCHAR(32) | 渠道 |
| resource | VARCHAR(256) | 资源标识 |
| action | VARCHAR(32) | 操作类型 |
| result | VARCHAR(16) | allowed/denied |
| timestamp | DATETIME | 时间戳 |

---

## 5. 资源消耗声明

| 维度 | 评估 |
|:-----|:-----|
| 基础内存 | ~30MB（插件加载 + Casbin 引擎） |
| 运行时内存 | ~50MB（单次请求处理） |
| 数据库存储 | ~10MB/月（用户/角色/日志） |
| LLM Token | 每次对话 ~500 tokens |
| 最大并发 | 100 请求 |
| P95 响应时间 | <200ms（权限判断） |
| 最低配置 | 1核 CPU / 256MB RAM / 1GB 磁盘 |

---

## 6. 安全要求

1. 权限判断必须在每个业务数据查询前执行
2. 审计日志只 INSERT/SELECT，不可 UPDATE/DELETE
3. 外部用户（网站渠道）默认无业务数据权限
4. 拒绝话术不可暴露"有数据但没权限"
5. API 需要 Bearer Token 认证
