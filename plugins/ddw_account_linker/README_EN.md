# DDW Account Linker Plugin (ddw-account-linker v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P5-3** — Account mapping hub. Maps a customer company (`crm_companies`) to three downstream account kinds: user, SaaS tenant, or on-premise instance. Powers cross-system account linking, uniqueness checks, and lifecycle management.

## Description

- **Base Info**: link_type (user / saas_tenant / on_premise_instance), external_id, external_name
- **Uniqueness**: unique within `(tenant_id, link_type, external_id)` to prevent duplicate bindings
- **Company Link**: optional `crm_companies.id`; preserved on company delete/archive (ON DELETE SET NULL)
- **Extensibility**: `metadata_json` stores arbitrary JSON (instance specs, tenant region, business tags)
- **Status Machine**: `active` / `inactive`; soft delete → `inactive` (audit trail retained)
- **Multi-tenant Isolation**: data isolation by `tenant_id`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /account-links | Create account link |
| GET | /account-links | List (paginated + filter: company_id / link_type / status) |
| GET | /account-links/stats | Statistics (total / active / inactive + by_link_type) |
| GET | /account-links/by-company/{company_id} | All links for a company (any status) |
| GET | /account-links/{id} | Link details |
| DELETE | /account-links/{id} | Soft delete (status=inactive) |

Note: `/stats` and `/by-company/{cid}` must be registered before `/{id}`, otherwise FastAPI will route `stats` as id.

## Data Model

`AccountLink` table (`crm_account_links`) core fields:

- **PK**: `id` (BigInt)
- **Tenant**: `tenant_id` (from `TenantMixin`)
- **Company**: `company_id` (FK → crm_companies.id, ON DELETE SET NULL)
- **Type**: `link_type` / `external_id` / `external_name`
- **Ext**: `metadata_json` (JSON dict)
- **Status**: `status` (active/inactive)
- **Audit**: `created_at` / `updated_at` (from `TimestampMixin`) / `created_by`

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| default_page_size | int | 20 | Default page size |
| link_types | array | [user, saas_tenant, on_premise_instance] | Link type enum |
| statuses | array | [active, inactive] | Status enum |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_account_linker/tests/ -v --tb=short
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
