# DDW License Core Plugin (ddw-license-core v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P4-2** — License full-lifecycle management.

## Description

- **Auto Numbering**: `license_no` (unique, LIC-YYYYMMDD-NNN)
- **Three License Types**: `trial` / `formal` / `renewal`
- **Status Machine**: `active` / `expired` / `suspended` / `revoked` / `renewed`
- **Auto Expiration Check**: cross-day cron or caller-triggered, expired licenses → `expired`
- **Renewal**: `POST /licenses/{id}/renew` creates new license, old → `renewed`
- **Suspend / Resume / Revoke**: `/suspend` `/resume` `/revoke` three endpoints
- **Plugin Entitlements**: `plugin_entitlements` (JSON) lists enabled plugins for the license
- **Multi-tenant Isolation**: data isolation by `tenant_id`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /licenses | Create license (auto license_no) |
| GET | /licenses | List (paginated + filter: type/status/company) |
| GET | /licenses/stats | Statistics |
| GET | /licenses/{id} | License details |
| PUT | /licenses/{id} | Update license |
| POST | /licenses/{id}/renew | Renew (new license + old → renewed) |
| POST | /licenses/{id}/suspend | Suspend |
| POST | /licenses/{id}/resume | Resume (suspended → active) |
| POST | /licenses/{id}/revoke | Revoke (active → revoked) |

## Data Model

`License` table (`crm_licenses`) core fields:

- **PK**: `id` (BigInt)
- **Number**: `license_no` (unique)
- **Tenant**: `tenant_id` (from `TenantMixin`)
- **Link**: `company_id` (FK → crm_companies.id, ON DELETE CASCADE)
- **Type**: `license_type` (trial/formal/renewal)
- **Scope**: `product_ids` (JSON list) / `plugin_entitlements` (JSON list)
- **Capacity**: `max_users` / `max_nodes`
- **Validity**: `valid_from` / `valid_to` (Date)
- **Status**: `status` (active/expired/suspended/revoked/renewed)
- **Audit**: `created_at` / `updated_at` (from `TimestampMixin`)

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| default_page_size | int | 20 | Default page size |
| license_types | array | [trial, formal, renewal] | License type enum |
| statuses | array | [active, expired, suspended, revoked, renewed] | Status enum |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_license_core/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.models.TimestampMixin` — timestamps
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter
- `sdk.plugin_base.PluginBase` — plugin base class
- `plugins.ddw_company_profile` — soft dependency (FK to crm_companies.id)

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
