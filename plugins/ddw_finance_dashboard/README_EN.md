# DDW Finance Dashboard Plugin (ddw-finance-dashboard v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P1-6** — Finance aggregation queries. Built on contract / receivable / payment tables to provide all the metrics a finance dashboard needs.

## Description

- **Overview**: contract amount, receivable, received, overdue, receivable unreceived
- **Overdue List**: all overdue receivable plans, ordered by overdue days desc
- **Trend**: contract signing / receivable / received amounts in the last N months
- **Stats**: status distribution, top-N companies by unreceived amount
- **No new table**: read-only queries on P1-1 / P1-3 / P1-4

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| GET | /dashboard/overview | Overview (contract / receivable / received / overdue / unreceived) |
| GET | /dashboard/overdue | Overdue receivable list |
| GET | /dashboard/trend | Trend data (last N months) |
| GET | /dashboard/stats | Stats (status distribution + top-N companies) |

## Data Model

**No new table**, read-only on:

- **P1-1 `crm_contracts`**: contract amount, signing time, status
- **P1-3 `crm_receivables`**: receivable amount, paid amount, due date, status
- **P1-4 `crm_offline_pos_records`**: received amount, matched amount, payment date

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| trend_window_months | int | 12 | Trend lookback months |
| overdue_limit | int | 100 | Overdue list default limit |
| contract_signed_statuses | array | [signed, active, completed] | Contract "signed" coverage |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_finance_dashboard/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter
- `sdk.plugin_base.PluginBase` — plugin base class
- `plugins.ddw_company_profile` / `plugins.ddw_contract_core` / `plugins.ddw_order` / `plugins.ddw_receivable` / `plugins.ddw_offline_pos` — required

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
