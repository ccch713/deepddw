# DDW Partner Directory Plugin (ddw-partner-directory v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P2-1** — Reseller onboarding, level, product scope, discount configuration.

## Description

- **Base Info**: Partner type (reseller/agent/distributor), level (normal/silver/gold/strategic), region, industry
- **Discounts**: product / plugin / service discount (percentage, 80 = 80% off)
- **Allowed Products**: JSON list
- **Agreement Period**: agreement_start / agreement_end
- **Contact**: contact_person + contact_phone
- **Status Management**: active / inactive / suspended (soft delete → suspended)
- **Multi-tenant Isolation**: data isolation by `tenant_id`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /partners | Create partner |
| GET | /partners | List partners (paginated + filter) |
| GET | /partners/{id} | Partner details |
| PUT | /partners/{id} | Update partner |
| DELETE | /partners/{id} | Soft delete (status=suspended) |
| GET | /partners/stats | Statistics |

## Data Model

`Partner` table (`crm_partners`) core fields:

- **PK**: `id` (BigInt)
- **Tenant**: `tenant_id` (from `TenantMixin`)
- **Company**: `company_id` (FK → crm_companies.id, ON DELETE SET NULL)
- **Type**: `partner_type` / `level`
- **Region/Industry**: `region` / `industry`
- **Scope**: `allowed_products` (JSON list)
- **Discounts**: `product_discount` / `plugin_discount` / `service_discount` (Numeric(5,2))
- **Agreement**: `agreement_start` / `agreement_end` (Date)
- **Contact**: `contact_person` / `contact_phone`
- **Status**: `status` (active/inactive/suspended)
- **Audit**: `created_at` / `updated_at` (from `TimestampMixin`)

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| default_partner_type | string | reseller | Default type |
| default_level | string | normal | Default level |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_partner_directory/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.models.TimestampMixin` — timestamps
- `sdk.plugin_base.PluginBase` — plugin base class

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
