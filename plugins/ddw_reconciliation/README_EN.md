# DDW Reconciliation Plugin (ddw-reconciliation v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P1-5** — Receivable / Payment reconciliation (matching).

## Description

- **Auto Match Recommend**: precise match by amount + company for unreconciled receivables and payments
- **Confirm**: transactional update of `receivable.paid_amount` + `payment.matched_amount` + both status machines
- **Cancel**: revert a confirmed reconciliation
- **History**: in-memory (cleared on restart) log of all recon / cancel actions
- **Unmatched Summary**: pending items by receivable / payment dimension
- **No new table**: directly reads / writes P1-3 `crm_receivables` and P1-4 `crm_offline_pos_records`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /reconciliation/match | Match recommendation (by company + amount) |
| POST | /reconciliation/confirm | Confirm (transactional) |
| POST | /reconciliation/cancel | Cancel |
| GET | /reconciliation/history | History (in-memory, filterable by company_id / date) |
| GET | /reconciliation/unmatched | Unmatched summary (receivable / payment split) |

## Data Model

**No new table**, operates on:

- **P1-3 `crm_receivables`**: `amount` / `paid_amount` / `status` (pending/partial/overdue/paid)
- **P1-4 `crm_offline_pos_records`**: `amount` / `matched_amount` / `status` (pending/matched/partial)

## Status Machine Coupling

- receivable fully paid → `paid`
- receivable partial → `partial`
- payment fully matched → `matched`
- payment partial → `partial`

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| max_match_per_request | int | 20 | Max matches per confirm |
| allow_overpay | bool | false | Allow receivable overpay (strict default) |
| receivable_matchable_statuses | array | [pending, partial, overdue] | Receivable matchable statuses |
| payment_matchable_statuses | array | [pending, partial] | Payment matchable statuses |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_reconciliation/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter
- `sdk.plugin_base.PluginBase` — plugin base class
- `plugins.ddw_company_profile` — soft dependency
- `plugins.ddw_receivable` / `plugins.ddw_offline_pos` — required dependencies

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
