# DDW Invoice Plugin (ddw-invoice v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P5-2** — Sales-side invoice application and invoice record management.

## Description

- **Workflow**: `requested` (application) → `issued` (upload invoice file) → `voided` (cancel)
- **Invoice Type**: `special` (special VAT invoice 增值税专用发票) / `normal` (general VAT invoice 增值税普通发票)
- **Price-Tax Split**: `amount` (excluding tax) / `tax_amount` / `total_amount`
- **Multi-dim Filter**: by company / order / status / type / invoice date
- **Auto Numbering**: invoice_no
- **Multi-tenant Isolation**: data isolation by `tenant_id`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /invoices | New invoice application (status=requested) |
| GET | /invoices | List (paginated + multi-dim filter) |
| GET | /invoices/stats | Statistics (static path, before /{id}) |
| GET | /invoices/{id} | Invoice details |
| PUT | /invoices/{id} | Update (only requested) |
| POST | /invoices/{id}/upload | Upload invoice (requested → issued) |
| POST | /invoices/{id}/void | Void (issued → voided) |

## Data Model

`Invoice` table (`crm_invoices`) core fields:

- **PK**: `id` (BigInt)
- **Tenant**: `tenant_id` (from `TenantMixin`)
- **Links**: `company_id` (FK → crm_companies.id, ON DELETE CASCADE) / `order_id` (FK → crm_orders.id, nullable)
- **Numbering**: `invoice_no` (unique)
- **Type**: `invoice_type` (special/normal)
- **Amount**: `amount` / `tax_amount` / `total_amount`
- **Info**: `invoice_title` / `tax_id` / `invoice_url` (file URL)
- **Time**: `issued_at` (Date)
- **Status**: `status` (requested/issued/voided)
- **Audit**: `created_at` (from `TimestampMixin`)

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| default_page_size | int | 20 | Default page size |
| invoice_types | array | [special, normal] | Invoice type enum |
| statuses | array | [requested, issued, voided] | Status enum |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_invoice/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.models.TimestampMixin` — timestamps
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter
- `sdk.plugin_base.PluginBase` — plugin base class
- `plugins.ddw_company_profile` / `plugins.ddw_order` — soft dependencies

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
