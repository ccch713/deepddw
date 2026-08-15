# DDW 应收管理插件（ddw-receivable v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P1-3** —— 应收（Receivable）全生命周期管理。

## 功能描述

- **应收节点**：`node_name` 字段标识节点（首款 / 部署款 / 验收款 / 续费款 / 尾款）
- **部分收款与全额收款**：`paid_amount` 字段记录已收金额
- **逾期自动标记**：超过 `due_date` 且未全额收款的应收自动置 `overdue`
- **状态机**：`pending` / `partial` / `paid` / `overdue`
- **与企业/订单/合同可选关联**：ON DELETE SET NULL（订单/合同删除后应收保留）
- **多维筛选**：按企业 / 订单 / 合同 / 状态 / 到期日范围
- **统计概览**：应收 / 已收 / 未收 / 逾期
- **多租户隔离**：基于 `tenant_id` 的数据隔离

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /receivables | 新建应收 |
| GET | /receivables | 列表（分页 + 多维筛选） |
| GET | /receivables/stats | 统计概览 |
| GET | /receivables/overdue | 逾期清单 |
| GET | /receivables/{id} | 应收详情 |
| PUT | /receivables/{id} | 更新应收 |

## 数据模型

`Receivable` 表（`crm_receivables`）核心字段：

- **主键**：`id` (BigInt)
- **租户**：`tenant_id` (来自 `TenantMixin`)
- **关联**：`company_id` (FK → crm_companies.id, ON DELETE CASCADE) / `order_id` (FK → crm_orders.id, ON DELETE SET NULL) / `contract_id` (FK → crm_contracts.id, ON DELETE SET NULL)
- **节点**：`plan_name` / `node_name`
- **金额**：`amount` / `paid_amount` (Numeric(12,2))
- **时间**：`due_date` (Date)
- **状态**：`status` (pending/partial/paid/overdue)
- **审计**：`created_at` / `updated_at` (来自 `TimestampMixin`)

## 安装方法

插件随 DDW AI Hub 平台一起发布，无需独立安装。

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| default_tenant_id | int | 1 | 默认租户 |
| default_page_size | int | 20 | 列表默认分页大小 |
| statuses | array | [pending, partial, paid, overdue] | 应收状态枚举 |
| node_names | array | [首款, 部署款, 验收款, 续费款, 尾款] | 常见节点名称（仅展示参考） |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_receivable/tests/ -v --tb=short
```

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户
- `core.database.models.TimestampMixin` —— 时间戳
- `core.database.tenant_filter.bypass_tenant_filter` —— 绕过租户过滤
- `sdk.plugin_base.PluginBase` —— 插件基类
- `plugins.ddw_company_profile` / `plugins.ddw_order` / `plugins.ddw_contract_core` —— 软依赖

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
