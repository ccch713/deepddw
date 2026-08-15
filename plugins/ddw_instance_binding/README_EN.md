# DDW Instance Binding Plugin (ddw-instance-binding v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P4-3** — Binds a customer company / license to a runtime instance (cloud SaaS tenant or on-premise deployment).

## Description

- **Two Instance Types**: `saas` (cloud SaaS tenant) / `on-premise` (local deployment)
- **Relations**: instance attaches to a customer company + license
- **Status Machine**: `active` / `inactive` / `suspended`; soft delete → `suspended` (audit trail retained)
- **Heartbeat**: `POST /instances/{id}/heartbeat` records `last_heartbeat` from client
- **Environment Tag**: `production` / `staging` / `test`
- **Multi-dim Filter**: by company / license / type / environment / status
- **Multi-tenant Isolation**: data isolation by `tenant_id`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /instances | Create instance binding |
| GET | /instances | List (paginated + multi-dim filter) |
| GET | /instances/stats | Statistics |
| GET | /instances/{id} | Instance details |
| PUT | /instances/{id} | Update instance |
| DELETE | /instances/{id} | Soft delete (status=suspended) |
| POST | /instances/{id}/heartbeat | Heartbeat |

## Data Model

`Instance` table (`crm_instances`) core fields:

- **PK**: `id` (BigInt)
- **Tenant**: `tenant_id` (from `TenantMixin`)
- **Links**: `company_id` (FK → crm_companies.id, ON DELETE CASCADE) / `license_id` (FK → crm_licenses.id, nullable)
- **Type**: `instance_type` (saas/on-premise) / `instance_id` (external) / `instance_name`
- **Fingerprint**: `fingerprint` (anti-forgery)
- **Environment**: `environment` (production/staging/test)
- **Endpoint**: `endpoint`
- **Status**: `status` (active/inactive/suspended) / `last_heartbeat` (timestamp)
- **Audit**: `created_at` / `updated_at` (from `TimestampMixin`)

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| default_page_size | int | 20 | Default page size |
| instance_types | array | [saas, on-premise] | Instance type enum |
| environments | array | [production, staging, test] | Environment enum |
| statuses | array | [active, inactive, suspended] | Status enum |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_instance_binding/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.models.TimestampMixin` — timestamps
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter
- `sdk.plugin_base.PluginBase` — plugin base class
- `plugins.ddw_company_profile` / `plugins.ddw_license_core` — soft dependencies

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
