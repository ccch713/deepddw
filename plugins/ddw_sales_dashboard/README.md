# DDW 销售看板插件（ddw-sales-dashboard v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P0-5** —— 销售端聚合查询层 / 销售仪表盘。

## 功能描述

**本插件是只读聚合查询层，不创建任何新表**。直接对 P0-1~P0-4 四个插件的
数据进行 SQL 聚合，提供销售仪表盘所需的 6 类统计指标：

- **总览（Overview）**：企业 / 联系人 / 商机 / 报价单 数量 + 预计 / 成交 / 报价接受金额 + 成交客户数（去重）
- **漏斗（Funnel）**：按商机阶段（含 won / lost 终止态）分组的 count + total_amount
- **趋势（Trend）**：最近 N 个月（默认 12）的新增商机数 / 总金额 / 成交金额（按 `won_at` 归属月份）
- **销售排行（Ranking）**：按 `owner_id` 聚合的预计金额 / 成交金额 / 成交率（`win_rate`）
- **最近商机（Recent）**：按 `updated_at` 倒序的 N 条商机，LEFT JOIN 拿企业名
- **阶段分布（Stage Distribution）**：与漏斗同口径但用 `stage_distribution` 专用 schema，适配前端饼图 / 环图

## 与 P0-3 漏斗接口的差异

| 维度 | P0-3 `funnel` | P0-5 `funnel` |
|------|--------------|--------------|
| 范围 | 仅 `status='open'` 进行中 | 全量（含 `won` / `lost` 终止态） |
| 视角 | 销售管道（按 stage 推进） | Dashboard 视角（看整体分布） |
| 排序 | 严格按 STAGE_DISPLAY_ORDER | 同 |

## API 端点

所有端点位于 `/api/v1/plugins/ddw-sales-dashboard` 前缀下。

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/dashboard/overview` | 销售总览 |
| GET | `/dashboard/funnel` | 商机漏斗（全量） |
| GET | `/dashboard/trend?months=12` | 最近 N 月趋势 |
| GET | `/dashboard/ranking` | 销售排行（按 owner 聚合） |
| GET | `/dashboard/recent?limit=10` | 最近商机 |
| GET | `/dashboard/stage-distribution` | 阶段分布（饼图数据） |

## 数据源（依赖 P0-1~P0-4）

| 表 | 来源插件 | 关键字段 |
|----|----------|----------|
| `crm_companies` | P0-1 | `id` / `name` / `tenant_id` |
| `crm_contacts` | P0-2 | `id` / `tenant_id` |
| `crm_opportunities` | P0-3 | `id` / `tenant_id` / `stage` / `status` / `estimated_amount` / `owner_id` / `company_id` / `created_at` / `updated_at` / `won_at` |
| `crm_quotations` | P0-4 | `id` / `tenant_id` / `status` / `final_amount` |

阶段常量与顺序复用 P0-3 暴露的 `STAGE_DISPLAY_ORDER` / `STAGE_LABELS`，保证
看板漏斗顺序与商机管理插件的漏斗图保持一致。

## 关键设计决策

1. **不创建新表**：`models.py` 为空占位，文件保留以备未来扩展
2. **金额 SQL 端聚合**：所有金额字段走 `func.coalesce(func.sum(...), 0)`，
   避免 Python 端 float 精度漂移
3. **趋势月份连续无空洞**：用 Python 端生成 12 个月份键，缺失月份补 0
4. **ranking 排除 `owner_id IS NULL`**：无法归因的商机不参与排行
5. **win_rate 仅基于终止态**：`won_count / (won_count + lost_count)`，
   进行中商机不计入分母
6. **LEFT JOIN 拉企业名**：recent 接口的企业被归档/删除时 `company_name` 为 `None`
7. **租户过滤**：所有查询都带 `tenant_id` 条件，配合 `bypass_tenant_filter()`
   在跨租户统计时按需关闭全局过滤

## 目录结构

```
plugins/ddw_sales_dashboard/
├── __init__.py          # VERSION, PLUGIN_NAME
├── manifest.yaml        # 插件元数据
├── plugin.py            # PluginBase 子类
├── models.py            # 空占位（本插件不创建新表）
├── schemas.py           # 6 类响应 Pydantic schema
├── services.py          # DashboardService：6 个聚合查询方法
├── router.py            # 7 个 API 端点
├── tests/
│   ├── conftest.py      # 显式 import 4 个依赖插件的 models
│   └── test_dashboard.py  # 7 个测试
├── README.md
├── README_EN.md
└── LICENSE
```

## 依赖

- `core.database.session` — `Base` / `session_scope` / `bypass_tenant_filter`
- `core.database.models` — `Base` / `TenantMixin` / `TimestampMixin`
- `sdk.plugin_base` — `PluginBase`
- `plugins.ddw_company_profile.models` — `Company`
- `plugins.ddw_contact_hub.models` — `Contact`
- `plugins.ddw_opportunity.models` — `Opportunity`
- `plugins.ddw_opportunity.services` — `STAGE_DISPLAY_ORDER` / `STAGE_LABELS`
- `plugins.ddw_quotation.models` — `Quotation`

## 测试

```bash
# 仅本插件
python3 -m pytest plugins/ddw_sales_dashboard/tests/ -v

# 跨插件回归（P0-1~P0-4 + P0-5）
python3 -m pytest \
  plugins/ddw_company_profile/tests/ \
  plugins/ddw_contact_hub/tests/ \
  plugins/ddw_opportunity/tests/ \
  plugins/ddw_quotation/tests/ \
  plugins/ddw_sales_dashboard/tests/ -q
# 预期：57 passed
```

## 版本

- **v1.0.0**（2026-08-03）—— 初版，6 个聚合查询接口 + 1 个健康检查
