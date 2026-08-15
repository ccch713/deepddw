# DDW 应收实收核销插件（ddw-reconciliation v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P1-5** —— 应收（Receivable）与实收（Payment）的核销（对账）。

## 功能描述

- **自动匹配推荐**：按金额 + 公司精确匹配未核销应收单与未核销实收单，给出建议
- **确认核销**：事务中更新 `receivable.paid_amount` + `payment.matched_amount` + 双方状态机自动重算
- **取消核销**：撤销已确认的核销（refund 语义）
- **核销历史**：内存级（重启清空）记录所有核销/取消动作
- **未核销汇总**：分别按 receivable / payment 维度返回待核销项
- **本插件不创建新表**，直接读写 P1-3 `crm_receivables` 与 P1-4 `crm_offline_pos_records`

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /reconciliation/match | 匹配推荐（按公司+金额） |
| POST | /reconciliation/confirm | 确认核销（事务：双写 paid_amount / matched_amount + 状态机） |
| POST | /reconciliation/cancel | 取消核销 |
| GET | /reconciliation/history | 核销历史（内存级，可按 company_id / date 筛选） |
| GET | /reconciliation/unmatched | 未核销汇总（receivable / payment 分开） |

## 数据模型

**不创建新表**，操作：

- **P1-3 `crm_receivables`**：`amount` / `paid_amount` / `status` (pending/partial/overdue/paid)
- **P1-4 `crm_offline_pos_records`**：`amount` / `matched_amount` / `status` (pending/matched/partial)

## 状态机联动

- receivable 收款完成 → `paid`
- receivable 收部分款 → `partial`
- payment 完全核销 → `matched`
- payment 部分核销 → `partial`

## 安装方法

插件随 DDW AI Hub 平台一起发布，无需独立安装。

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| default_tenant_id | int | 1 | 默认租户 |
| max_match_per_request | int | 20 | 单次 confirm 允许的最大 match 条数 |
| allow_overpay | bool | false | 是否允许 receivable 收款超额（默认严格对账） |
| receivable_matchable_statuses | array | [pending, partial, overdue] | 允许被核销的应收状态 |
| payment_matchable_statuses | array | [pending, partial] | 允许核销到应收的实收状态 |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_reconciliation/tests/ -v --tb=short
```

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户
- `core.database.tenant_filter.bypass_tenant_filter` —— 绕过租户过滤
- `sdk.plugin_base.PluginBase` —— 插件基类
- `plugins.ddw_company_profile` —— 软依赖
- `plugins.ddw_receivable` / `plugins.ddw_offline_pos` —— 必依赖

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
