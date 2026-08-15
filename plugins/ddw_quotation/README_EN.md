# DDW Quotation Plugin (ddw-quotation v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P0-4** — Full lifecycle sales quotation management.

## Description

- **Master + Items (Child Table)**: structured normalization (vs. JSON items approach used by orders)
- **Auto Numbering**: `QT-YYYYMMDD-NNN` (NNN is daily sequence starting from 001)
- **Auto Calculation**: `total_amount` and `final_amount` (after discount) computed automatically
- **Discount Rate**: `discount_rate` (Numeric(5,2), 100 = no discount)
- **Status Machine**: `draft` → `sent` → `accepted` / `rejected` / `expired`
- **Multi-currency**: `currency` field (default CNY)
- **Validity**: `valid_until` (Date) — expiration logic
- **Links**: `company_id` (FK → crm_companies.id) / `contact_id` (nullable) / `opportunity_id` (nullable)
- **Multi-tenant Isolation**: data isolation by `tenant_id`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /quotations | Create quotation (with items) |
| GET | /quotations | List (paginated + filter) |
| GET | /quotations/stats | Statistics |
| GET | /quotations/{id} | Quotation details (with items) |
| PUT | /quotations/{id} | Update quotation |
| DELETE | /quotations/{id} | Delete quotation (only draft) |
| POST | /quotations/{id}/send | Mark as sent (draft → sent) |
| POST | /quotations/{id}/accept | Mark as accepted (sent → accepted) |
| POST | /quotations/{id}/reject | Mark as rejected (sent → rejected) |

## Data Model

`Quotation` table (`crm_quotations`) core fields:

- **PK**: `id` (BigInt)
- **Number**: `quotation_no` (unique, QT-YYYYMMDD-NNN)
- **Tenant**: `tenant_id` (from `TenantMixin`)
- **Links**: `company_id` (FK → crm_companies.id, ON DELETE CASCADE) / `contact_id` (FK → crm_contacts.id, nullable) / `opportunity_id` (FK → crm_opportunities.id, nullable)
- **Info**: `title` / `terms` / `notes`
- **Amount**: `total_amount` / `discount_rate` (Numeric(5,2), 100=no-discount) / `final_amount` (Numeric(12,2)) / `currency` (default CNY)
- **Validity**: `valid_until` (Date)
- **Status**: `status` (draft/sent/accepted/rejected/expired)
- **Time**: `sent_at` / `accepted_at`
- **Audit**: `created_at` / `updated_at` (from `TimestampMixin`)

`QuotationItem` table (`crm_quotation_items`) core fields:

- **PK**: `id` (BigInt)
- **FK**: `quotation_id` (FK → crm_quotations.id, ON DELETE CASCADE)
- **Product**: `product_name` / `product_type` (product/plugin/service/token) / `product_code`
- **Qty/Price**: `quantity` / `unit` (default 套) / `unit_price` / `amount` (Numeric(12,2))
- **Info**: `description` / `sort_order`

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| default_page_size | int | 20 | Default page size |
| default_discount_rate | number | 100 | Default discount rate (100 = no discount) |
| default_currency | string | CNY | Default currency |
| statuses | array | [draft, sent, accepted, rejected, expired] | Status enum |
| product_types | array | [product, plugin, service, token] | Item product type enum |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_quotation/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.models.TimestampMixin` — timestamps
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter
- `sdk.plugin_base.PluginBase` — plugin base class
- `plugins.ddw_company_profile` / `plugins.ddw_contact_hub` / `plugins.ddw_opportunity` — soft dependencies

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
