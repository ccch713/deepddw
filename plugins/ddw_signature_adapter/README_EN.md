# DDW Signature Adapter Plugin (ddw-signature-adapter v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P5-1** — E-signature service adapter layer. Bridges third-party e-signature providers: Tencent E-Sign / Dianxiaoyu / eSign / Manual.

## Description

- **Multi-provider Abstraction**: supports `tencent` (Tencent E-Sign) / `dianxiaoyu` (Dianxiaoyu) / `esign` (eSign) / `manual` (manual)
- **Request Lifecycle**: `pending` → `signing` → `signed` / `rejected` / `expired`
- **Async Callback**: `POST /signature-requests/{id}/callback` receives provider callback and updates status
- **Manual Upload**: `POST /signature-requests/{id}/manual-upload` allows manual upload of signed PDF
- **Adapter Reserved**: per-provider HTTP integration is extensible via adapter pattern (default stub)
- **Contract Link**: `contract_id` (FK → crm_contracts.id, ON DELETE CASCADE)
- **Multi-tenant Isolation**: data isolation by `tenant_id`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /signature-requests | Create signature request (no real third-party call) |
| GET | /signature-requests | List (paginated + filter) |
| GET | /signature-requests/stats | Statistics |
| GET | /signature-requests/{id} | Request details |
| PUT | /signature-requests/{id} | Update request (only pending) |
| POST | /signature-requests/{id}/callback | Third-party async callback |
| POST | /signature-requests/{id}/manual-upload | Manual upload of signed file |

## Data Model

`SignatureRequest` table (`crm_signature_requests`) core fields:

- **PK**: `id` (BigInt)
- **Tenant**: `tenant_id` (from `TenantMixin`)
- **Link**: `contract_id` (FK → crm_contracts.id, ON DELETE CASCADE)
- **Provider**: `provider` (tencent/dianxiaoyu/esign/manual) / `external_request_id`
- **Signers**: `signers` (JSON list)
- **Documents**: `document_url` (pending) / `signed_document_url` (signed)
- **Status**: `status` (pending/signing/signed/rejected/expired) / `signed_at`
- **Audit**: `created_at` (from `TimestampMixin`)

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| default_page_size | int | 20 | Default page size |
| providers | array | [tencent, dianxiaoyu, esign, manual] | Supported providers |
| statuses | array | [pending, signing, signed, rejected, expired] | Request status enum |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_signature_adapter/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.models.TimestampMixin` — timestamps
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter
- `sdk.plugin_base.PluginBase` — plugin base class
- `plugins.ddw_contract_core` — required dependency

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
