# DDW Receivable Plugin (ddw-receivable v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P1-3** — Receivable full-lifecycle management.

## Description

- **Receivable Nodes**: `node_name` field identifies nodes (首款 / 部署款 / 验收款 / 续费款 / 尾款)
- **Partial / Full Receipt**: `paid_amount` field tracks received amount
- **Auto Overdue Mark**: past `due_date` and not fully paid → `overdue`
- **Status Machine**: `pending` / `partial` / `paid` / `overdue`
- **Optional Links**: company / order / contract (ON DELETE SET NULL, retained when related records are deleted)
- **Multi-dim Filter**: by company / order / contract / status / due date range
- **Statistics**: receivable / received / unreceived / overdue
- **Multi-tenant Isolation**: data isolation by `tenant_id`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /receivables | Create receivable |
| GET | /receivables | List (paginated + multi-dim filter) |
| GET | /receivables/stats | Statistics |
| GET | /receivables/overdue | Overdue list |
| GET | /receivables/{id} | Receivable details |
| PUT | /receivables/{id} | Update receivable |

## Data Model

`Receivable` table (`crm_receivables`) core fields:

- **PK**: `id` (BigInt)
- **Tenant**: `tenant_id` (from `TenantMixin`)
- **Links**: `company_id` (FK → crm_companies.id, ON DELETE CASCADE) / `order_id` (FK → crm_orders.id, ON DELETE SET NULL) / `contract_id` (FK → crm_contracts.id, ON DELETE SET NULL)
- **Node**: `plan_name` / `node_name`
- **Amount**: `amount` / `paid_amount` (Numeric(12,2))
- **Time**: `due_date` (Date)
- **Status**: `status` (pending/partial/paid/overdue)
- **Audit**: `created_at` / `updated_at` (from `TimestampMixin`)

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| default_page_size | int | 20 | Default page size |
| statuses | array | [pending, partial, paid, overdue] | Status enum |
| node_names | array | [首款, 部署款, 验收款, 续费款, 尾款] | Common node names (display only) |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_receivable/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.models.TimestampMixin` — timestamps
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter
- `sdk.plugin_base.PluginBase` — plugin base class
- `plugins.ddw_company_profile` / `plugins.ddw_order` / `plugins.ddw_contract_core` — soft dependencies

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
