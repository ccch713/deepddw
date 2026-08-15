# DDW Token Entitlement Plugin (ddw-token-entitlement v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P4-4** — Customer / instance token entitlement allocation, usage tracking, and overage control.

## Description

- **Three Entitlement Types**: `platform` (platform-allocated) / `custom-key` (customer's own key) / `local-llm` (local LLM)
- **Allocation**: company / instance dimension total quota
- **Consume**: `POST /entitlements/{id}/consume` decrements on call; if `overage_allowed=true`, overage is permitted
- **Customer Key Masking**: `api_key_masked` stores only the masked key, raw key stays with customer
- **Local LLM Endpoint**: `llm_endpoint` records the local LLM service address
- **Multi-tenant Isolation**: data isolation by `tenant_id`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /entitlements | Create entitlement |
| GET | /entitlements | List (paginated + filter) |
| GET | /entitlements/stats | Statistics |
| GET | /entitlements/{id} | Entitlement details |
| PUT | /entitlements/{id} | Update entitlement |
| DELETE | /entitlements/{id} | Delete (hard) |
| POST | /entitlements/{id}/consume | Consume tokens |

## Data Model

`TokenEntitlement` table (`crm_token_entitlements`) core fields:

- **PK**: `id` (BigInt)
- **Tenant**: `tenant_id` (from `TenantMixin`)
- **Links**: `company_id` (FK → crm_companies.id, ON DELETE CASCADE) / `instance_id` (FK → crm_instances.id, nullable)
- **Type**: `entitlement_type` (platform/custom-key/local-llm)
- **Quota**: `allocated_tokens` / `used_tokens`
- **Overage**: `overage_allowed` (bool)
- **Credentials**: `api_key_masked` (masked key) / `llm_endpoint` (local LLM URL)
- **Audit**: `created_at` / `updated_at` (from `TimestampMixin`)

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| default_page_size | int | 20 | Default page size |
| entitlement_types | array | [platform, custom-key, local-llm] | Entitlement type enum |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_token_entitlement/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.models.TimestampMixin` — timestamps
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter
- `sdk.plugin_base.PluginBase` — plugin base class

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
