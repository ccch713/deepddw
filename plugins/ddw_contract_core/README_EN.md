# DDW Contract Core Plugin (ddw-contract-core v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P1-1** — Full lifecycle sales contract management.

## Description

- **Auto Numbering**: `CT-YYYYMMDD-NNN`
- **Contract Type**: `standard` (standard) / `framework` (framework agreement) / `supplementary` (supplementary)
- **Status Machine**: `draft` → `pending_approval` → `approved` → `signed` → `active` → `completed` / `terminated`; `draft` can also → `rejected` on reject
- **Attachments**: `attachments` (JSON list) for contract file references
- **Versioning**: `version` field (int, increment on supplementary)
- **Multi-currency**: `currency` (default CNY)
- **Time**: `signed_at` (timestamp) / `effective_from` / `effective_to` (Date)
- **Multi-tenant Isolation**: data isolation by `tenant_id`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /contracts | Create contract (auto contract_no) |
| GET | /contracts | List (paginated + filter) |
| GET | /contracts/stats | Statistics |
| GET | /contracts/{id} | Contract details |
| PUT | /contracts/{id} | Update contract |
| POST | /contracts/{id}/submit-approval | Submit for approval (draft → pending_approval) |
| POST | /contracts/{id}/approve | Approve (pending_approval → approved) |
| POST | /contracts/{id}/reject | Reject (pending_approval → rejected) |
| POST | /contracts/{id}/sign | Sign (approved → signed) |
| POST | /contracts/{id}/activate | Activate (signed → active) |
| POST | /contracts/{id}/terminate | Terminate (active → terminated) |
| POST | /contracts/{id}/complete | Complete (active → completed) |

## Data Model

`Contract` table (`crm_contracts`) core fields:

- **PK**: `id` (BigInt)
- **Number**: `contract_no` (unique, CT-YYYYMMDD-NNN)
- **Tenant**: `tenant_id` (from `TenantMixin`)
- **Links**: `company_id` (FK → crm_companies.id, ON DELETE CASCADE) / `contact_id` (FK → crm_contacts.id, nullable) / `opportunity_id` (FK → crm_opportunities.id, nullable) / `quotation_id` (FK → crm_quotations.id, nullable)
- **Info**: `title` / `contract_type` (standard/framework/supplementary) / `payment_terms` / `deliverables` / `sla`
- **Amount**: `total_amount` (Numeric(12,2)) / `currency` (default CNY)
- **Time**: `signed_at` / `effective_from` / `effective_to`
- **Files**: `attachments` (JSON list)
- **Versioning**: `version` (int, default 1)
- **Status**: `status` (draft/pending_approval/approved/signed/active/completed/terminated/rejected)
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
| statuses | array | [draft, pending_approval, approved, signed, active, completed, terminated, rejected] | Status enum |
| contract_types | array | [standard, framework, supplementary] | Contract type enum |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_contract_core/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.models.TimestampMixin` — timestamps
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter
- `sdk.plugin_base.PluginBase` — plugin base class
- `plugins.ddw_company_profile` / `plugins.ddw_contact_hub` / `plugins.ddw_opportunity` / `plugins.ddw_quotation` — soft dependencies

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
