# DDW 经销商开户插件（ddw-partner-directory v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P2-1** —— 经销商开户、等级、可售范围、折扣配置。

## 功能描述

- **基础信息**：经销商类型（reseller/agent/distributor）、等级（normal/silver/gold/strategic）、区域、行业
- **折扣配置**：产品折扣、插件折扣、售后折扣（百分数，80 = 8 折）
- **可售范围**：可售产品/插件清单（JSON 列表）
- **协议期**：agreement_start / agreement_end
- **联系人**：contact_person + contact_phone
- **状态管理**：active / inactive / suspended（软删除走 suspended）
- **多租户隔离**：基于 `tenant_id` 的数据隔离

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /partners | 新建经销商 |
| GET | /partners | 列表（分页 + 多维筛选） |
| GET | /partners/{id} | 经销商详情 |
| PUT | /partners/{id} | 更新经销商 |
| DELETE | /partners/{id} | 软删除（status=suspended） |
| GET | /partners/stats | 统计概览 |

## 数据模型

`Partner` 表（`crm_partners`）核心字段：

- **主键**：`id` (BigInt)
- **租户**：`tenant_id` (来自 `TenantMixin`)
- **关联企业**：`company_id` (FK → crm_companies.id, ON DELETE SET NULL)
- **类型**：`partner_type` (reseller/agent/distributor) / `level` (normal/silver/gold/strategic)
- **区域/行业**：`region` / `industry`
- **可售范围**：`allowed_products` (JSON list)
- **折扣**：`product_discount` / `plugin_discount` / `service_discount` (Numeric(5,2))
- **协议期**：`agreement_start` / `agreement_end` (Date)
- **联系人**：`contact_person` / `contact_phone`
- **状态**：`status` (active/inactive/suspended)
- **审计**：`created_at` / `updated_at` (来自 `TimestampMixin`)

## 安装方法

插件随 DDW AI Hub 平台一起发布。无需独立安装。

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| default_tenant_id | int | 1 | 默认租户 |
| default_partner_type | string | reseller | 默认类型 |
| default_level | string | normal | 默认等级 |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_partner_directory/tests/ -v --tb=short
```

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户
- `core.database.models.TimestampMixin` —— 时间戳
- `sdk.plugin_base.PluginBase` —— 插件基类

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
