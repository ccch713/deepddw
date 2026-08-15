# DDW Renewal & Alert Plugin (ddw-renewal v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P4-6** — Cross-plugin queries on `crm_licenses` and `crm_contracts` to provide renewal alerts and renewal management.

## Description

- **Expiring Soon**: licenses expiring in 30 / 60 / 90 days
- **Overdue**: licenses past `valid_to` but not yet renewed
- **Renewal Quote**: estimate based on historical contract amount + renewal duration
- **Renewal Stats**: renewal rate (renewals in last N days / expiries in last N days), renewal amount aggregation
- **No new table**: cross-plugin queries on P4-2 `crm_licenses` and P1-1 `crm_contracts`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| GET | /renewal/expiring | Expiring soon (default 30 days, configurable) |
| GET | /renewal/overdue | Overdue license list |
| POST | /renewal/quote | Generate renewal quote (based on history) |
| GET | /renewal/stats | Renewal stats (expiry windows + renewal rate) |

## Data Model

**No new table**, cross-plugin queries on:

- **P4-2 `crm_licenses`**: `valid_to` / `status` / `company_id` / `product_ids`
- **P1-1 `crm_contracts`**: `total_amount` / `effective_from` / `effective_to` / `company_id`

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| expiring_windows_days | array | [30, 60, 90] | Expiry windows (days) |
| renewal_rate_windows_days | array | [30, 60, 90] | Renewal rate window (days) |
| default_renewal_unit_days | int | 365 | Default renewal duration (days) |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_renewal/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter
- `sdk.plugin_base.PluginBase` — plugin base class
- `plugins.ddw_company_profile` / `plugins.ddw_license_core` / `plugins.ddw_contract_core` — required

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
