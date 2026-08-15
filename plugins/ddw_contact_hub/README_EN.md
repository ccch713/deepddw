# DDW Contact Hub Plugin (ddw-contact-hub v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P0-2** — Enterprise contact master data management.

## Description

End-to-end contact master data management for sales:

- **Basic info**: name, position, department, phone, email, WeChat
- **Company association**: optional `company_id` (nullable, supports independent contacts); FK `crm_companies.id` ON DELETE SET NULL
- **Primary flag**: `is_primary` marker (typically one per company)
- **Extended fields**: `tags` (JSON list) / `groups` (JSON list) / `notes`
- **Multi-dimensional filtering**: by status / company / is_primary / tag / group
- **Fuzzy search**: by name / phone / email / position / department; dedicated autocomplete endpoint
- **Company aggregation**: `by-company/{company_id}` returns all contacts of a company (primary first)
- **Statistics**: totals / status distribution / primary count / with_company / independent / by_company
- **Multi-tenant isolation**: data isolation by `tenant_id` (via SQLAlchemy event hooks)
- **Hard delete**: `DELETE` performs physical removal (per task spec; contacts have no critical business dependencies)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/contacts` | Create contact |
| GET | `/contacts` | List contacts (paginated + filter + search) |
| GET | `/contacts/search?q=` | Search by name/phone/email (autocomplete) |
| GET | `/contacts/by-company/{company_id}` | All contacts of a company |
| GET | `/contacts/stats` | Statistics overview |
| GET | `/contacts/{id}` | Contact details |
| PUT | `/contacts/{id}` | Update contact |
| DELETE | `/contacts/{id}` | Hard delete contact |

## Data Model

`Contact` table (`crm_contacts`) core fields:

- **PK**: `id` (BigInt, auto-increment)
- **Tenant**: `tenant_id` (from `TenantMixin`, FK to `tenants.id`, ON DELETE CASCADE)
- **Association**: `company_id` (FK `crm_companies.id`, ON DELETE SET NULL, nullable, indexed)
- **Basic**: `name` (required, indexed) / `phone` (indexed) / `email` (indexed) / `position` / `department` / `wechat`
- **Extended**: `tags` (JSON list) / `groups` (JSON list) / `is_primary` / `notes`
- **Status**: `status` (active/inactive/archived)
- **Audit**: `created_at` / `updated_at` (from `TimestampMixin`) / `created_by`

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

Dev mode activation:
1. Ensure `plugins/ddw_contact_hub/manifest.yaml` exists
2. Platform startup `core/main.py:load_plugins()` auto-discovers and loads
3. **Plugin dependency**: `ddw-company-profile` (contact's `company_id` references `crm_companies.id`)

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_tenant_id` | int | 1 | Default tenant |
| `default_page_size` | int | 20 | Default list page size |
| `statuses` | array | `[active, inactive, archived]` | Status enum |
| `max_tags_per_contact` | int | 20 | Max tags per contact |
| `max_groups_per_contact` | int | 10 | Max groups per contact |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_contact_hub/tests/ -v --tb=short
```

Coverage:
- ✅ Create (independent / with company)
- ✅ List (pagination / filter by company / fuzzy search)
- ✅ Detail (exists / not found)
- ✅ Update (success / not found)
- ✅ Hard delete
- ✅ by-company endpoint (primary first)
- ✅ Statistics overview

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.models.TimestampMixin` — timestamps
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter (dev/admin only)
- `sdk.plugin_base.PluginBase` — plugin base class
- `ddw-company-profile` — plugin dependency (FK `crm_companies.id`)

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
