# DDW 合同中心插件（ddw-contract-core v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P1-1** —— 销售端合同全生命周期管理。

## 功能描述

提供销售侧合同主数据全生命周期管理能力：

- **合同主数据**：自动生成单号（CT-YYYYMMDD-NNN）、合同标题、合同类型（standard / framework / supplementary）、总金额、币种
- **合同状态机**：8 个状态（draft / pending_approval / approved / signed / active / completed / terminated / rejected），按定义好的合法迁移路径流转，自动记录审批/签署/激活/完成/终止时间戳
- **时间与条款**：生效起止日期、付款条款、交付物、SLA
- **审计字段**：reject_reason / terminate_reason 等原因记录
- **附件管理**：attachments（JSON list）支持任意数量 URL
- **多维筛选**：按状态、合同类型、关联企业 ID 筛选
- **模糊搜索**：按单号 / 标题模糊匹配
- **统计概览**：各状态计数 + 按 contract_type 分组 + 总金额 / 激活金额 / 完成金额
- **多租户隔离**：基于 `tenant_id` 的数据隔离（SQLAlchemy 事件钩子自动注入/过滤）
- **版本号**：version 字段，初始 1

## 合同状态机

```
draft ──submit_approval──> pending_approval ──approve──> approved ──sign──> signed
                                  │                                              │
                                  └──reject──> rejected ──> draft                ├──activate──> active
                                                                                │                │
                                                                                └──terminate──────┴──terminate──> terminated
                                                                                                                 │
                                                                                                                 ▼
                                                                                                              completed
```

合法迁移路径（`ALLOWED_TRANSITIONS`）：

| from | to |
|------|------|
| `draft` | `pending_approval` |
| `pending_approval` | `approved` / `rejected` |
| `approved` | `signed` |
| `signed` | `active` / `terminated` |
| `active` | `completed` / `terminated` |
| `rejected` | `draft`（打回重做） |
| `completed` | （终止态，不可迁移） |
| `terminated` | （终止态，不可迁移） |

非法迁移抛 `ValueError("invalid transition: x -> y")`。

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/contracts` | 新建合同（status=draft） |
| GET | `/contracts` | 合同列表（分页 + 筛选 + 搜索） |
| GET | `/contracts/stats` | 合同统计概览 |
| GET | `/contracts/{id}` | 合同详情 |
| PUT | `/contracts/{id}` | 更新合同（仅 draft / rejected 状态可改） |
| POST | `/contracts/{id}/submit-approval` | 提交审批（draft → pending_approval） |
| POST | `/contracts/{id}/approve` | 审批通过（pending_approval → approved） |
| POST | `/contracts/{id}/reject` | 审批驳回（pending_approval → rejected, reason 必填） |
| POST | `/contracts/{id}/sign` | 标记已签（approved → signed） |
| POST | `/contracts/{id}/activate` | 激活合同（signed → active） |
| POST | `/contracts/{id}/terminate` | 终止合同（signed / active → terminated, reason 必填） |
| POST | `/contracts/{id}/complete` | 完成合同（active → completed） |

## 数据模型

`Contract` 表（`crm_contracts`）核心字段：

- **主键**：`id` (BigInt, 自增)
- **租户**：`tenant_id` (来自 `TenantMixin`，外键 `tenants.id`，ON DELETE CASCADE)
- **业务关联**：`company_id` / `contact_id` / `opportunity_id` / `quotation_id`（外键 ON DELETE SET NULL，关联对象删除不级联删合同）
- **单号 / 标题**：`contract_no` (唯一, 格式 `CT-YYYYMMDD-NNN`) / `title`
- **类型 / 金额**：`contract_type` (standard/framework/supplementary) / `total_amount` (Numeric(12,2)) / `currency`
- **时间 / 条款**：`signed_at` / `effective_from` / `effective_to` / `payment_terms` / `deliverables` / `sla`
- **扩展**：`attachments` (JSON list) / `notes` / `version` (default=1)
- **状态机字段**：`status` / `approved_at` / `rejected_at` / `reject_reason` / `activated_at` / `completed_at` / `terminated_at` / `terminate_reason`
- **审计**：`created_at` / `updated_at` (来自 `TimestampMixin`) / `created_by`

## 安装方法

插件随 DDW AI Hub 平台一起发布。无需独立安装。

开发模式启用：
1. 确保 `plugins/ddw_contract_core/manifest.yaml` 存在
2. 平台启动时 `core/main.py:load_plugins()` 会自动扫描并加载

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `default_tenant_id` | int | 1 | 默认租户 |
| `default_page_size` | int | 20 | 列表默认分页大小 |
| `default_currency` | string | `CNY` | 默认币种 |
| `statuses` | array | `[draft, pending_approval, approved, signed, active, completed, terminated, rejected]` | 合同状态枚举 |
| `contract_types` | array | `[standard, framework, supplementary]` | 合同类型枚举 |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_contract_core/tests/ -v --tb=short
```

跨插件回归测试：

```bash
python -m pytest plugins/ddw_company_profile/tests/ \
                plugins/ddw_contact_hub/tests/ \
                plugins/ddw_opportunity/tests/ \
                plugins/ddw_quotation/tests/ \
                plugins/ddw_sales_dashboard/tests/ \
                plugins/ddw_contract_core/tests/ -q
```

测试覆盖：
- ✅ 创建（正常 / 单号格式 / 单号唯一性）
- ✅ 列表（分页 / 按状态筛选）
- ✅ 详情
- ✅ 更新（draft 状态可改 / active 状态被阻止）
- ✅ 状态机（合法迁移 / 非法迁移 / 终止态保护 / 未知目标 / 白盒 ALLOWED_TRANSITIONS 完整性）
- ✅ 提交审批 / 审批通过 / 驳回（reason 必填）
- ✅ 标记已签（验证 signed_at 时间戳）
- ✅ 激活合同
- ✅ 终止合同（reason 必填）
- ✅ 统计概览（各状态计数 + by_type + 金额汇总）

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户
- `core.database.models.TimestampMixin` —— 时间戳
- `core.database.tenant_filter.bypass_tenant_filter` —— 绕过租户过滤（仅限开发/admin）
- `sdk.plugin_base.PluginBase` —— 插件基类
- 依赖上游插件：`ddw_company_profile` / `ddw_contact_hub` / `ddw_opportunity` / `ddw_quotation`（外键引用，独立测试时由 conftest 用占位表兜底）

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
