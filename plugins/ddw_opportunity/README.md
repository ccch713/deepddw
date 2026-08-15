# DDW 商机管理插件（ddw-opportunity v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P0-3** —— 销售商机（Opportunity）全生命周期管理。

## 功能描述

提供销售侧商机全生命周期管理能力：

- **商机主数据**：名称、来源（直销/经销商/官网/展会/转介绍）、负责人、预计金额、预计成交日
- **阶段流转**：8 段管道 `initial_contact → demand_confirmation → proposal_submitted → quotation_sent → negotiation → contract_pending → won/lost`
- **probability 自动同步**：调用 `PUT /opportunities/{id}/stage` 时，probability 会按阶段表自动重写，避免两个字段脱钩
- **成交 / 丢单**：`/win` 标记成交（status=won, stage=won, won_at=now, probability=100）；`/lose` 标记丢单（lost_reason 必填）
- **关闭**：`DELETE` 走软关闭（status=closed）
- **多维筛选**：按 owner_id、stage、status、company_id 筛选
- **模糊搜索**：按商机名称模糊匹配
- **漏斗统计**：`GET /opportunities/funnel` 按阶段管道顺序展示 count + total_amount
- **概览统计**：`GET /opportunities/stats` 给出 total / open / won / lost / closed + total_amount + won_amount + 各维度分组
- **多租户隔离**：基于 `tenant_id` 的数据隔离（SQLAlchemy 事件钩子自动注入/过滤）
- **关联**：`company_id`（→ `crm_companies.id`）、`contact_id`（→ `crm_contacts.id`），外键可空

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/opportunities` | 新建商机 |
| GET | `/opportunities` | 商机列表（分页 + 筛选 + 搜索） |
| GET | `/opportunities/funnel` | 漏斗统计（按 stage，含 count + total_amount） |
| GET | `/opportunities/stats` | 统计概览（total/open/won/lost + total_amount + won_amount + by_stage） |
| GET | `/opportunities/{id}` | 商机详情 |
| PUT | `/opportunities/{id}` | 更新商机 |
| DELETE | `/opportunities/{id}` | 关闭商机（status=closed） |
| PUT | `/opportunities/{id}/stage` | 更新阶段（**自动同步 probability**） |
| POST | `/opportunities/{id}/win` | 标记成交（status=won, stage=won, won_at=now） |
| POST | `/opportunities/{id}/lose` | 标记丢单（status=lost, stage=lost, lost_reason 必填） |

## 数据模型

`Opportunity` 表（`crm_opportunities`）核心字段：

- **主键**：`id` (BigInt, 自增)
- **租户**：`tenant_id` (来自 `TenantMixin`，外键 `tenants.id`，ON DELETE CASCADE)
- **关联**：`company_id` (FK→`crm_companies.id` ON DELETE SET NULL) / `contact_id` (FK→`crm_contacts.id` ON DELETE SET NULL)
- **基本信息**：`name` (indexed) / `source` / `owner_id` (indexed)
- **金额 / 阶段**：`estimated_amount` (Numeric(12,2)) / `stage` (indexed) / `probability` (0-100)
- **时间 / 描述 / 标签**：`expected_close_date` / `description` / `tags` (JSON list)
- **状态 / 结果**：`status` (open/won/lost/closed) / `won_at` / `lost_reason`
- **审计**：`created_at` / `updated_at` (来自 `TimestampMixin`) / `created_by`

## 阶段 → 默认 probability 映射（核心）

| stage code | 中文标签 | probability |
|------------|----------|-------------|
| `initial_contact` | 初步接触 | 10 |
| `demand_confirmation` | 需求确认 | 20 |
| `proposal_submitted` | 方案提交 | 40 |
| `quotation_sent` | 报价已发 | 60 |
| `negotiation` | 商务谈判 | 75 |
| `contract_pending` | 合同待签 | 90 |
| `won` | 成交 | 100 |
| `lost` | 丢单 | 0 |

`PUT /opportunities/{id}/stage` 会**自动**按本表重写 probability，调用方无法通过该端点覆盖。

## 安装方法

插件随 DDW AI Hub 平台一起发布。无需独立安装。

开发模式启用：
1. 确保 `plugins/ddw_opportunity/manifest.yaml` 存在
2. 平台启动时 `core/main.py:load_plugins()` 会自动扫描并加载
3. **依赖插件**：`ddw-company-profile`（外键 `crm_companies.id`）

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `default_tenant_id` | int | 1 | 默认租户 |
| `default_page_size` | int | 20 | 列表默认分页大小 |
| `stages` | array | 见上表 8 项 | 商机阶段枚举 |
| `statuses` | array | `[open, won, lost, closed]` | 商机状态枚举 |
| `sources` | array | `[直销, 经销商, 官网, 展会, 转介绍]` | 商机来源 |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_opportunity/tests/ -v --tb=short
```

测试覆盖（12 个）：
- ✅ 新建（无 company/contact）
- ✅ 列表分页
- ✅ 按 owner_id 筛选
- ✅ 按 stage 筛选
- ✅ 详情
- ✅ 更新
- ✅ **更新 stage 自动同步 probability**
- ✅ 标记成交（验证 won_at 时间戳）
- ✅ 标记丢单（验证 lost_reason 必填）
- ✅ 关闭（status=closed）
- ✅ 漏斗统计
- ✅ 概览统计

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户
- `core.database.models.TimestampMixin` —— 时间戳
- `core.database.tenant_filter.bypass_tenant_filter` —— 绕过租户过滤（仅限开发/admin）
- `sdk.plugin_base.PluginBase` —— 插件基类
- `plugins.ddw_company_profile` —— 软依赖（外键 `crm_companies.id`）

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
