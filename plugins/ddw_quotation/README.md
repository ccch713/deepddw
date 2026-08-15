# DDW 报价单管理插件（ddw-quotation v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P0-4** —— 报价单全生命周期管理。

## 功能描述

提供销售侧报价单（Quotation）从创建到关闭的端到端能力：

- **主-子结构**：主表 `crm_quotations`（Quotation）+ 明细表 `crm_quotation_items`（QuotationItem）；明细不独立携带 tenant_id，跟随主表
- **业务关联**：可选外键到 `crm_companies`（客户企业）、`crm_contacts`（联系人）、`crm_opportunities`（商机），`ON DELETE SET NULL`
- **自动单号**：服务端按 `QT-YYYYMMDD-NNN` 规则生成当日递增单号（NNN 从 001 开始）
- **金额自动计算**：
  - 行金额 `amount = quantity × unit_price`（用户可覆盖）
  - 总金额 `total_amount = sum(items.amount)`
  - 折后金额 `final_amount = total_amount × discount_rate / 100`
- **状态机**：`draft → sent → accepted/rejected/expired`；状态迁移自动写时间戳（sent_at / accepted_at / rejected_at）
- **明细级联**：更新报价单时 items 整体替换；删除报价单时 items 通过 FK CASCADE 自动清理（**硬删除**）
- **多维筛选**：按状态、企业 ID 过滤；按单号/标题模糊搜索
- **统计概览**：各状态计数 + 所有 final_amount 之和 + 已接受 final_amount 之和
- **多租户隔离**：主表继承 `TenantMixin`，明细跟随主表

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET  | `/health` | 健康检查 |
| POST | `/quotations` | 新建报价单（含 items） |
| GET  | `/quotations` | 列表（分页 + 搜索 + 筛选） |
| GET  | `/quotations/stats` | 统计概览 |
| GET  | `/quotations/{id}` | 详情（含 items） |
| PUT  | `/quotations/{id}` | 更新（items 级联重建） |
| DELETE | `/quotations/{id}` | 硬删除（CASCADE 清明细） |
| POST | `/quotations/{id}/send` | 标记已发送（draft → sent） |
| POST | `/quotations/{id}/accept` | 标记已接受（sent → accepted） |
| POST | `/quotations/{id}/reject` | 标记已拒绝（draft/sent → rejected） |

## 数据模型

### `Quotation` 主表（`crm_quotations`）

- **主键**：`id` (BigInt, 自增)
- **租户**：`tenant_id`（来自 `TenantMixin`，外键 `tenants.id`，`ON DELETE CASCADE`）
- **业务关联**：`company_id` / `contact_id` / `opportunity_id`（均为可选外键，`ON DELETE SET NULL`）
- **单号**：`quotation_no` (String 30, unique, 格式 `QT-YYYYMMDD-NNN`)
- **标题**：`title` (String 200)
- **金额**：`total_amount` (Numeric 12,2) / `discount_rate` (Numeric 5,2, 默认 100) / `final_amount` (Numeric 12,2) / `currency` (String 10, 默认 `CNY`)
- **商务**：`valid_until` (Date) / `terms` (Text) / `notes` (Text)
- **状态**：`status` (draft/sent/accepted/rejected/expired) / `sent_at` / `accepted_at` / `rejected_at`
- **审计**：`created_at` / `updated_at`（来自 `TimestampMixin`）/ `created_by`

### `QuotationItem` 明细表（`crm_quotation_items`，**不**继承 `TenantMixin`）

- **主键**：`id` (BigInt, 自增)
- **归属**：`quotation_id`（外键 `crm_quotations.id`，`ON DELETE CASCADE`）
- **产品**：`product_name` / `product_type` (product/plugin/service/token) / `product_code`
- **数量单价**：`quantity` / `unit` / `unit_price` / `amount`
- **描述排序**：`description` / `sort_order`
- **审计**：`created_at`

## 业务规则

1. **新建必带 items**：`items` 至少 1 条，否则 `ValueError`
2. **金额计算**：服务端自动算 `total_amount` 与 `final_amount`，用户传入仅作参考
3. **更新 items 级联**：
   - `items` 不传：保留现有明细
   - `items = []`：清空明细
   - `items = [...]`：删旧插新 + 重算金额
4. **删除是硬删除**：DB FK CASCADE 自动清理 items
5. **状态机**：
   - `send`：仅 `draft` 可调用
   - `accept`：仅 `sent` 可调用
   - `reject`：`draft` / `sent` 可调用
   - 非法迁移抛 `ValueError`（router 转 409）

## 安装方法

插件随 DDW AI Hub 平台一起发布，无需独立安装。

开发模式启用：
1. 确保 `plugins/ddw_quotation/manifest.yaml` 存在
2. 平台启动时 `core/main.py:load_plugins()` 会自动扫描并加载
3. 路由前缀：`/api/v1/plugins/ddw-quotation`

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `default_tenant_id` | int | 1 | 默认租户 |
| `default_page_size` | int | 20 | 列表默认分页大小 |
| `default_discount_rate` | number | 100 | 默认折扣率（百分比，100 = 不打折） |
| `default_currency` | string | `CNY` | 默认币种 |
| `statuses` | array | `[draft, sent, accepted, rejected, expired]` | 状态枚举 |
| `product_types` | array | `[product, plugin, service, token]` | 明细产品类型枚举 |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python3 -m pytest plugins/ddw_quotation/tests/ -v --tb=short
```

测试覆盖（12 个用例）：

- ✅ 创建（多明细 + 外键关联）
- ✅ 单号自动生成（格式 + 递增）
- ✅ 单号唯一性（DB unique 约束）
- ✅ 总金额自动计算
- ✅ 折后金额（折扣率生效）
- ✅ 列表（分页 + 搜索 + 状态过滤）
- ✅ 详情（含 items 排序）
- ✅ 更新（items 级联重建 + 金额重算）
- ✅ 状态机：标记已发送
- ✅ 状态机：标记已接受
- ✅ 删除（硬删除 + FK CASCADE 清明细）
- ✅ 统计概览

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户（仅主表继承）
- `core.database.models.TimestampMixin` —— 时间戳
- `core.database.tenant_filter.bypass_tenant_filter` —— 绕过租户过滤（仅限开发/admin）
- `sdk.plugin_base.PluginBase` —— 插件基类

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
