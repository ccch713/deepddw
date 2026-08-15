# DDW 产品与插件目录插件（ddw-product-catalog v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P4-1** —— 产品/插件目录主数据。DDW 自研产品（DDW 底座、DDW 插件、Token 套餐）与第三方产品/服务统一管理。

## 功能描述

- **统一编码**：`code` 字段全局唯一，作为跨插件引用锚
- **产品类型**：`package`（套餐）/ `plugin`（插件）/ `service`（服务）/ `token`（Token 套餐）
- **价格管理**：`unit_price` (Numeric(12,2)) + `unit`（单位：套/年、套/月、个、次、万元、元）
- **版本控制**：`version` 字段记录主版本
- **激活开关**：`is_active` 控制上下架
- **扩展字段**：`metadata` (JSON) 存技术规格/许可范围/集成方式等任意信息
- **多租户隔离**：基于 `tenant_id` 的数据隔离

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /products | 新建产品 |
| GET | /products | 列表（分页 + 筛选：type/is_active/keyword） |
| GET | /products/stats | 统计概览 |
| GET | /products/{id} | 产品详情 |
| PUT | /products/{id} | 更新产品 |
| DELETE | /products/{id} | 软删除（is_active=false） |

## 数据模型

`Product` 表（`crm_products`）核心字段：

- **主键**：`id` (BigInt)
- **编码**：`code` (unique, indexed)
- **租户**：`tenant_id` (来自 `TenantMixin`)
- **类型**：`product_type` (package/plugin/service/token)
- **基本信息**：`name` / `description` / `version`
- **价格**：`unit_price` (Numeric(12,2)) / `unit` (套/年等)
- **状态**：`is_active` (bool)
- **扩展**：`metadata` (JSON)
- **审计**：`created_at` / `updated_at` (来自 `TimestampMixin`)

## 安装方法

插件随 DDW AI Hub 平台一起发布，无需独立安装。

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| default_tenant_id | int | 1 | 默认租户 |
| default_page_size | int | 20 | 列表默认分页大小 |
| product_types | array | [package, plugin, service, token] | 产品类型枚举 |
| default_units | array | [套/年, 套/月, 套, 个, 次, 万元, 元] | 常用单位参考 |
| max_unit_price | number | 99999999.99 | 单价上限（Numeric(12,2) 边界值） |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_product_catalog/tests/ -v --tb=short
```

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户
- `core.database.models.TimestampMixin` —— 时间戳
- `core.database.tenant_filter.bypass_tenant_filter` —— 绕过租户过滤
- `sdk.plugin_base.PluginBase` —— 插件基类

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
