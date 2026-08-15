# DDW 财务看板插件（ddw-finance-dashboard v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P1-6** —— 财务聚合查询。基于合同 / 应收 / 实收三张表的数据，提供财务仪表盘所需的全部统计指标。

## 功能描述

- **总览（overview）**：合同金额、应收金额、实收金额、逾期金额、应收未收
- **逾期列表（overdue）**：所有逾期的应收计划，按逾期天数倒序
- **趋势（trend）**：最近 N 月合同签约额 / 应收额 / 实收额
- **统计（stats）**：按状态分布、按企业未收金额 Top N
- **不创建新表**，只读查询 P1-1 / P1-3 / P1-4 三张表

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| GET | /dashboard/overview | 总览（合同总额 / 应收 / 实收 / 逾期 / 未收） |
| GET | /dashboard/overdue | 逾期应收列表（按逾期天数倒序） |
| GET | /dashboard/trend | 趋势数据（最近 N 月） |
| GET | /dashboard/stats | 统计（状态分布 + 企业未收 Top N） |

## 数据模型

**不创建新表**，只读查询：

- **P1-1 `crm_contracts`**：合同金额、签约时间、状态
- **P1-3 `crm_receivables`**：应收金额、已收金额、到期日、状态
- **P1-4 `crm_offline_pos_records`**：实收金额、核销金额、付款日期

## 安装方法

插件随 DDW AI Hub 平台一起发布，无需独立安装。

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| default_tenant_id | int | 1 | 默认租户 |
| trend_window_months | int | 12 | 趋势接口默认回看月数 |
| overdue_limit | int | 100 | 逾期列表默认返回条数 |
| contract_signed_statuses | array | [signed, active, completed] | 合同"已签"统计覆盖的状态集合 |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_finance_dashboard/tests/ -v --tb=short
```

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户
- `core.database.tenant_filter.bypass_tenant_filter` —— 绕过租户过滤
- `sdk.plugin_base.PluginBase` —— 插件基类
- `plugins.ddw_company_profile` / `plugins.ddw_contract_core` / `plugins.ddw_order` / `plugins.ddw_receivable` / `plugins.ddw_offline_pos` —— 必依赖

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
