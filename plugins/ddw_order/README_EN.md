# DDW Order Plugin (ddw-order v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P1-2** — Sales-side order full-lifecycle management.

## Description

- **JSON Items**: line items stored as JSON (vs the separate child table approach used by quotation); simpler for read-heavy workflows
- **Auto Numbering**: `ORD-YYYYMMDD-NNN`
- **Auto Total**: total_amount auto-computed from items
- **Status Machine**: `pending` → `confirmed` → `delivered` → `completed`; any non-terminal state can → `cancelled`
- **Cancel Reason**: cancellation must include a reason
- **Multi-currency**: `currency` field (default CNY)
- **Multi-tenant Isolation**: data isolation by `tenant_id`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /orders | Create order (auto-generate order_no + total) |
| GET | /orders | List (paginated + multi-dim filter) |
| GET | /orders/stats | Statistics |
| GET | /orders/{id} | Order details |
| PUT | /orders/{id} | Update (only non-terminal) |
| DELETE | /orders/{id} | Cancel (any non-terminal, requires reason) |
| POST | /orders/{id}/confirm | Confirm (pending → confirmed) |
| POST | /orders/{id}/deliver | Deliver (confirmed → delivered) |
| POST | /orders/{id}/complete | Complete (delivered → completed) |

## Data Model

`Order` table (`crm_orders`) core fields:

- **PK**: `id` (BigInt)
- **Order No**: `order_no` (unique, ORD-YYYYMMDD-NNN)
- **Tenant**: `tenant_id` (from `TenantMixin`)
- **Links**: `company_id` (FK → crm_companies.id, ON DELETE CASCADE) / `contract_id` (FK → crm_contracts.id, nullable)
- **Info**: `title`
- **Amount**: `total_amount` (Numeric(12,2)) / `currency` (default CNY)
- **Items**: `items` (JSON list: product/plugin/service + qty + unit_price)
- **Status**: `status` (pending/confirmed/delivered/completed/cancelled)
- **Time**: `confirmed_at` / `delivered_at`
- **Cancel**: `notes` (cancellation reason if cancelled)
- **Audit**: `created_at` / `updated_at` (from `TimestampMixin`)

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| default_page_size | int | 20 | Default page size |
| default_currency | string | CNY | Default currency |
| statuses | array | [pending, confirmed, delivered, completed, cancelled] | Status enum |
| terminal_statuses | array | [completed, cancelled] | Terminal statuses (no further transitions) |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_order/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.models.TimestampMixin` — timestamps
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter
- `sdk.plugin_base.PluginBase` — plugin base class
- `plugins.ddw_company_profile` / `plugins.ddw_contract_core` — soft dependencies

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
