# DDW Opportunity Plugin (ddw-opportunity v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P0-3** — Sales opportunity lifecycle management.

## Description

End-to-end opportunity lifecycle management for sales:

- **Master data**: name, source (direct/dealer/website/expo/referral), owner, estimated amount, expected close date
- **Stage pipeline**: 8 stages `initial_contact → demand_confirmation → proposal_submitted → quotation_sent → negotiation → contract_pending → won/lost`
- **Auto probability sync**: `PUT /opportunities/{id}/stage` rewrites probability from the stage table; the two fields never drift apart
- **Won / lost**: `/win` marks as won (status=won, stage=won, won_at=now, probability=100); `/lose` requires `lost_reason`
- **Close**: `DELETE` soft-closes (status=closed)
- **Multi-dimensional filtering**: by owner_id / stage / status / company_id
- **Fuzzy search**: by opportunity name
- **Funnel stats**: `GET /opportunities/funnel` returns per-stage count + total_amount in pipeline order
- **Overview stats**: `GET /opportunities/stats` returns total / open / won / lost / closed + total_amount + won_amount + by_stage
- **Multi-tenant isolation**: data isolation by `tenant_id` (via SQLAlchemy event hooks)
- **Relations**: `company_id` (→ `crm_companies.id`), `contact_id` (→ `crm_contacts.id`), both nullable

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/opportunities` | Create opportunity |
| GET | `/opportunities` | List opportunities (paginated + filter + search) |
| GET | `/opportunities/funnel` | Funnel stats (per stage, count + total_amount) |
| GET | `/opportunities/stats` | Overview stats |
| GET | `/opportunities/{id}` | Opportunity details |
| PUT | `/opportunities/{id}` | Update opportunity |
| DELETE | `/opportunities/{id}` | Close opportunity (status=closed) |
| PUT | `/opportunities/{id}/stage` | Update stage (**auto-syncs probability**) |
| POST | `/opportunities/{id}/win` | Mark as won |
| POST | `/opportunities/{id}/lose` | Mark as lost (lost_reason required) |

## Data Model

`Opportunity` table (`crm_opportunities`) core fields:

- **PK**: `id` (BigInt, auto-increment)
- **Tenant**: `tenant_id` (from `TenantMixin`, FK to `tenants.id`, ON DELETE CASCADE)
- **Relations**: `company_id` (FK→`crm_companies.id` ON DELETE SET NULL) / `contact_id` (FK→`crm_contacts.id` ON DELETE SET NULL)
- **Master**: `name` (indexed) / `source` / `owner_id` (indexed)
- **Money / stage**: `estimated_amount` (Numeric(12,2)) / `stage` (indexed) / `probability` (0-100)
- **Time / desc / tags**: `expected_close_date` / `description` / `tags` (JSON list)
- **State / result**: `status` (open/won/lost/closed) / `won_at` / `lost_reason`
- **Audit**: `created_at` / `updated_at` (from `TimestampMixin`) / `created_by`

## Stage → Default Probability Mapping (Core)

| stage code | label | probability |
|------------|-------|-------------|
| `initial_contact` | Initial contact | 10 |
| `demand_confirmation` | Demand confirmation | 20 |
| `proposal_submitted` | Proposal submitted | 40 |
| `quotation_sent` | Quotation sent | 60 |
| `negotiation` | Negotiation | 75 |
| `contract_pending` | Contract pending | 90 |
| `won` | Won | 100 |
| `lost` | Lost | 0 |

`PUT /opportunities/{id}/stage` automatically rewrites probability from this table; the caller cannot override it.

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

Dev mode activation:
1. Ensure `plugins/ddw_opportunity/manifest.yaml` exists
2. Platform startup `core/main.py:load_plugins()` auto-discovers and loads
3. **Plugin dependency**: `ddw-company-profile` (FK to `crm_companies.id`)

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_tenant_id` | int | 1 | Default tenant |
| `default_page_size` | int | 20 | Default list page size |
| `stages` | array | see 8-row table above | Stage enum |
| `statuses` | array | `[open, won, lost, closed]` | Status enum |
| `sources` | array | `[direct, dealer, website, expo, referral]` | Source enum |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_opportunity/tests/ -v --tb=short
```

Coverage (12 tests):
- ✅ Create (no company/contact)
- ✅ List pagination
- ✅ Filter by owner_id
- ✅ Filter by stage
- ✅ Detail
- ✅ Update
- ✅ **Stage update auto-syncs probability**
- ✅ Mark as won (verify won_at timestamp)
- ✅ Mark as lost (verify lost_reason required)
- ✅ Close (status=closed)
- ✅ Funnel stats
- ✅ Overview stats

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.models.TimestampMixin` — timestamps
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter (dev/admin only)
- `sdk.plugin_base.PluginBase` — plugin base class
- `plugins.ddw_company_profile` — soft dependency (FK to `crm_companies.id`)

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
