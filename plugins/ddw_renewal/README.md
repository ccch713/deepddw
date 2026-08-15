# DDW 续费与预警插件（ddw-renewal v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P4-6** —— 跨插件查询 crm_licenses 与 crm_contracts，提供续费预警与续费管理能力。

## 功能描述

- **即将到期清单**：未来 30 / 60 / 90 天到期的许可证清单
- **已逾期清单**：已超过 valid_to 但还未续费的许可证
- **续费报价估算**：基于历史合同金额 + 续费时长生成报价
- **续费统计**：续费率（最近 N 天续费数 / 最近 N 天到期数）、续费金额聚合
- **不创建新表**，跨插件查询 P4-2 crm_licenses 与 P1-1 crm_contracts

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| GET | /renewal/expiring | 即将到期（默认 30 天，可指定） |
| GET | /renewal/overdue | 已逾期许可证清单 |
| POST | /renewal/quote | 生成续费报价（基于历史合同） |
| GET | /renewal/stats | 续费统计（到期窗口 + 续费率） |

## 数据模型

**不创建新表**，跨插件查询：

- **P4-2 `crm_licenses`**：`valid_to` / `status` / `company_id` / `product_ids`
- **P1-1 `crm_contracts`**：`total_amount` / `effective_from` / `effective_to` / `company_id`

## 安装方法

插件随 DDW AI Hub 平台一起发布，无需独立安装。

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| default_tenant_id | int | 1 | 默认租户 |
| expiring_windows_days | array | [30, 60, 90] | 续费统计概览的到期窗口（天） |
| renewal_rate_windows_days | array | [30, 60, 90] | 续费率分子分母时间窗 |
| default_renewal_unit_days | int | 365 | 续费报价默认时长（天） |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_renewal/tests/ -v --tb=short
```

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户
- `core.database.tenant_filter.bypass_tenant_filter` —— 绕过租户过滤
- `sdk.plugin_base.PluginBase` —— 插件基类
- `plugins.ddw_company_profile` / `plugins.ddw_license_core` / `plugins.ddw_contract_core` —— 必依赖

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
