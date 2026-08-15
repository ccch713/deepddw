# DDW 订单管理插件（ddw-order v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P1-2** —— 订单全生命周期管理。

## 功能描述

提供销售侧订单（Order）从创建到完成/取消的端到端能力：

- **单表 + JSON 明细**：主表 `crm_orders`（Order）；明细 `items` 用 JSON 列存储（dict list），与 P0-4 报价单的子表模式不同——订单明细通常较短、变动少，JSON 更轻
- **业务关联**：可选外键到 `crm_companies`（客户企业）、`crm_contracts`（合同），`ON DELETE SET NULL`
- **自动单号**：服务端按 `ORD-YYYYMMDD-NNN` 规则生成当日递增单号（NNN 从 001 开始）
- **金额自动计算**：`total_amount = sum(item.amount or item.quantity × item.unit_price)`
- **状态机**：
  - `pending → confirmed → delivered → completed`（正向流转）
  - `pending / confirmed → cancelled`（任意非终态可取消，**必须填写原因**）
  - `completed / cancelled` 为终态
  - 状态迁移自动写时间戳（`confirmed_at` / `delivered_at` / `completed_at` / `cancelled_at`）
- **更新限制**：**仅 pending 状态可改**字段（confirmed / delivered / completed / cancelled 一律拒绝编辑）
- **多维筛选**：按状态、企业 ID、合同 ID 过滤；按单号/标题模糊搜索
- **统计概览**：各状态计数 + 所有 `total_amount` 之和 + 已完成 `total_amount` 之和
- **多租户隔离**：主表继承 `TenantMixin`

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET  | `/health` | 健康检查 |
| POST | `/orders` | 新建订单（status=pending） |
| GET  | `/orders` | 列表（分页 + 搜索 + 筛选） |
| GET  | `/orders/stats` | 统计概览 |
| GET  | `/orders/{id}` | 详情（含 items） |
| PUT  | `/orders/{id}` | 更新（仅 pending 可改，items 整体替换） |
| DELETE | `/orders/{id}` | 取消订单（pending/confirmed → cancelled，**body 必传 reason**） |
| POST | `/orders/{id}/confirm` | 确认（pending → confirmed） |
| POST | `/orders/{id}/deliver` | 交付（confirmed → delivered） |
| POST | `/orders/{id}/complete` | 完成（delivered → completed） |

## 数据模型

### `Order` 主表（`crm_orders`）

- **主键**：`id` (BigInt, 自增)
- **租户**：`tenant_id`（来自 `TenantMixin`，外键 `tenants.id`，`ON DELETE CASCADE`）
- **业务关联**：`company_id` / `contract_id`（均为可选外键，`ON DELETE SET NULL`，走 `use_alter=True`）
- **单号**：`order_no` (String 30, unique, 格式 `ORD-YYYYMMDD-NNN`)
- **标题**：`title` (String 200)
- **金额**：`total_amount` (Numeric 12,2)
- **明细**：`items` (JSON, list of dict: `product_name` / `quantity` / `unit_price` / `amount`)
- **状态**：`status` (pending/confirmed/delivered/completed/cancelled)
  - `confirmed_at` / `delivered_at` / `completed_at` / `cancelled_at` (DateTime, nullable)
  - `cancel_reason` (String 500)
- **备注审计**：`notes` (Text) / `created_by` / `created_at` / `updated_at`（后两个来自 `TimestampMixin`）

## 业务规则

### 状态机合法迁移

```
pending    → confirmed, cancelled
confirmed  → delivered, cancelled
delivered  → completed
completed  → (终态)
cancelled  → (终态)
```

非法迁移抛 `ValueError`（HTTP 400）。

### 取消订单

- 仅 `pending` / `confirmed` 状态可取消
- 请求体 **必须** 含 `reason`（min_length=1, max_length=500）
- 取消后 `cancelled_at` 写入当前时间，`cancel_reason` 写入原因
- `cancelled` 为终态，不可再迁移

### 更新订单

- 仅 `pending` 状态可调用 PUT
- `items` 字段在请求中：整体替换，传 `[]` 清空（total=0），非空则重算 `total_amount`
- `items` 字段不在请求中：保留现有 items，total 不变

### 自动单号

```
ORD-{YYYYMMDD}-{NNN}
         ↑          ↑
         今日日期    当日序号（001 起）
```

通过 SQL `LIKE 'ORD-YYYYMMDD-%'` 查询当日最大序号 + 1；DB unique 约束兜底并发碰撞。

## 配置项（manifest.yaml）

```yaml
default_tenant_id: 1
default_page_size: 20
default_currency: CNY
statuses: [pending, confirmed, delivered, completed, cancelled]
terminal_statuses: [completed, cancelled]
```

## 跨插件约定

- **依赖**：`core.database.models.Base` / `TenantMixin` / `TimestampMixin`；`core.database.session.session_scope` / `bypass_tenant_filter`
- **关联表**：`crm_companies`（由 `ddw_company_profile` 提供）、`crm_contracts`（由 `ddw_contract_core` 提供）
- **API 前缀**：`/api/v1/plugins/ddw-order`

## 测试

```bash
# 单独跑
python3 -m pytest plugins/ddw_order/tests/ -v

# 跨插件回归（销售 CRM 全套）
python3 -m pytest plugins/ddw_company_profile/tests/ \
                 plugins/ddw_contact_hub/tests/ \
                 plugins/ddw_opportunity/tests/ \
                 plugins/ddw_quotation/tests/ \
                 plugins/ddw_sales_dashboard/tests/ \
                 plugins/ddw_order/tests/ -q
# 期望 72 passed
```

测试覆盖（15 个用例）：
1. `test_create_order` - 新建
2. `test_order_no_auto_generation` - 单号格式 ORD-YYYYMMDD-NNN
3. `test_order_no_uniqueness` - 单号唯一性
4. `test_total_amount_with_items` - items 金额累加
5. `test_list_orders` - 列表（分页 + 搜索 + 多维筛选）
6. `test_get_order_detail` - 详情
7. `test_update_order_pending` - 更新 pending 状态
8. `test_state_machine_valid_transitions` - 合法迁移完整流程
9. `test_state_machine_invalid_transition` - 非法迁移抛错
10. `test_confirm_order` - 确认
11. `test_deliver_order` - 交付
12. `test_complete_order` - 完成
13. `test_cancel_order` - 取消
14. `test_cancel_requires_reason` - 取消 reason 必填
15. `test_stats_overview` - 统计
