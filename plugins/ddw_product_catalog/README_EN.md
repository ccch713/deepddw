# DDW Product Catalog Plugin (ddw-product-catalog v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P4-1** — Product / plugin catalog master data. Unified management of DDW self-developed products (DDW Hub, DDW plugins, Token plans) and third-party products/services.

## Description

- **Unified Code**: `code` field globally unique, acts as cross-plugin reference anchor
- **Product Types**: `package` / `plugin` / `service` / `token`
- **Price Management**: `unit_price` (Numeric(12,2)) + `unit` (套/年, 套/月, 个, 次, 万元, 元)
- **Versioning**: `version` field for major version
- **Active Toggle**: `is_active` for activation/deactivation
- **Extensibility**: `metadata` (JSON) for tech specs / license scope / integration details
- **Multi-tenant Isolation**: data isolation by `tenant_id`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /products | Create product |
| GET | /products | List (paginated + filter: type/is_active/keyword) |
| GET | /products/stats | Statistics |
| GET | /products/{id} | Product details |
| PUT | /products/{id} | Update product |
| DELETE | /products/{id} | Soft delete (is_active=false) |

## Data Model

`Product` table (`crm_products`) core fields:

- **PK**: `id` (BigInt)
- **Code**: `code` (unique, indexed)
- **Tenant**: `tenant_id` (from `TenantMixin`)
- **Type**: `product_type` (package/plugin/service/token)
- **Info**: `name` / `description` / `version`
- **Price**: `unit_price` (Numeric(12,2)) / `unit` (套/年 etc.)
- **Status**: `is_active` (bool)
- **Ext**: `metadata` (JSON)
- **Audit**: `created_at` / `updated_at` (from `TimestampMixin`)

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| default_page_size | int | 20 | Default page size |
| product_types | array | [package, plugin, service, token] | Product type enum |
| default_units | array | [套/年, 套/月, 套, 个, 次, 万元, 元] | Common units |
| max_unit_price | number | 99999999.99 | Max unit price (Numeric(12,2) boundary) |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_product_catalog/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.models.TimestampMixin` — timestamps
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter
- `sdk.plugin_base.PluginBase` — plugin base class

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
