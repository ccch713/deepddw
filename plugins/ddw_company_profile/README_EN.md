# DDW Company Profile Plugin (ddw-company-profile v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P0-1** — Enterprise master data management.

## Description

End-to-end enterprise master data management for sales:

- **Business registration**: Full registered name, Unified Social Credit Code (18 chars), company type, registered address, legal representative, established date, business scope, business license attachment
- **Certification status**: pending / submitted / approved / rejected / expired (timestamps auto-recorded)
- **Invoice info**: Invoice title, tax ID, bank name, bank account, company phone, mailing address
- **Business fields**: industry, company size, registered capital, annual revenue
- **Multi-dimensional filtering**: by status / certification / company type / industry
- **Fuzzy search**: by name / short name / credit code / legal representative
- **Statistics**: totals / status distribution / certification distribution / company type / industry
- **Multi-tenant isolation**: data isolation by `tenant_id` (via SQLAlchemy event hooks)
- **Soft delete**: `DELETE` archives (status=archived), no physical removal

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/companies` | Create company |
| GET | `/companies` | List companies (paginated + filter + search) |
| GET | `/companies/search?q=` | Search by name/credit code (autocomplete) |
| GET | `/companies/stats` | Statistics overview |
| GET | `/companies/{id}` | Company details |
| PUT | `/companies/{id}` | Update company |
| DELETE | `/companies/{id}` | Archive company (soft delete) |

## Data Model

`Company` table (`crm_companies`) core fields:

- **PK**: `id` (BigInt, auto-increment)
- **Tenant**: `tenant_id` (from `TenantMixin`, FK to `tenants.id`, ON DELETE CASCADE)
- **Registration**: `name` / `credit_code` (unique) / `short_name` / `company_type` / `registered_address` / `legal_representative` / `established_date` / `business_license_url` / `business_scope`
- **Certification**: `certification_status` / `certification_submitted_at` / `certification_approved_at` / `certification_expires_at`
- **Invoice**: `invoice_title` / `tax_id` / `bank_name` / `bank_account` / `company_phone` / `company_address`
- **Business**: `industry` / `company_size` / `registered_capital` / `annual_revenue`
- **Extended**: `tags` (JSON list) / `notes` / `status` (active/inactive/archived)
- **Audit**: `created_at` / `updated_at` (from `TimestampMixin`) / `created_by` / `updated_by`

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

Dev mode activation:
1. Ensure `plugins/ddw_company_profile/manifest.yaml` exists
2. Platform startup `core/main.py:load_plugins()` auto-discovers and loads

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_tenant_id` | int | 1 | Default tenant |
| `default_page_size` | int | 20 | Default list page size |
| `certification_statuses` | array | `[pending, submitted, approved, rejected, expired]` | Certification enum |
| `company_types` | array | `[有限公司, 股份公司, 个体工商户, 合伙企业, 国有企业]` | Company type enum |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_company_profile/tests/ -v --tb=short
```

Coverage:
- ✅ Create (success / duplicate credit_code)
- ✅ List (pagination / search / filter)
- ✅ Detail (exists / not found)
- ✅ Update (success / not found)
- ✅ Archive
- ✅ Search autocomplete
- ✅ Statistics overview

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.models.TimestampMixin` — timestamps
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter (dev/admin only)
- `sdk.plugin_base.PluginBase` — plugin base class

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
