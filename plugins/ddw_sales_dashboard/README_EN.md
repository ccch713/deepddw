# DDW Sales Dashboard Plugin (ddw-sales-dashboard v1.0.0)

DDW AI Hub Sales CRM plugin set **P0-5** — read-only aggregation layer that
powers the sales dashboard.

## Overview

This plugin is a **read-only aggregation layer** — it does **not** create any
new tables. It directly queries the four upstream plugins (P0-1~P0-4) via
SQLAlchemy and exposes six aggregated indicators:

- **Overview**: counts (companies / contacts / opportunities / quotations) +
  estimated / won / accepted amounts + won-customers (distinct)
- **Funnel**: per-stage breakdown (includes `won` / `lost` terminal states)
  with count + total_amount
- **Trend**: rolling N-month (default 12) of new opportunities, total amount
  and won amount (won amount is bucketed by `won_at`, not `created_at`)
- **Ranking**: per-`owner_id` rollup — estimated / won amount and `win_rate`
- **Recent**: top-N opportunities by `updated_at` (LEFT JOIN to `crm_companies`
  for company name)
- **Stage Distribution**: same shape as funnel but with a dedicated schema
  suited for pie / donut charts

## Difference vs. P0-3 Funnel

| Aspect | P0-3 `funnel` | P0-5 `funnel` |
|--------|--------------|--------------|
| Scope | `status='open'` only (in pipeline) | All statuses (includes `won` / `lost`) |
| Use case | Sales pipeline (left-to-right) | Dashboard view (overall distribution) |
| Ordering | Strict `STAGE_DISPLAY_ORDER` | Same |

## API Endpoints

Base path: `/api/v1/plugins/ddw-sales-dashboard`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness probe |
| GET | `/dashboard/overview` | Sales overview |
| GET | `/dashboard/funnel` | Opportunity funnel (all statuses) |
| GET | `/dashboard/trend?months=12` | Last N months trend |
| GET | `/dashboard/ranking` | Sales ranking by owner |
| GET | `/dashboard/recent?limit=10` | Recent opportunities |
| GET | `/dashboard/stage-distribution` | Stage distribution (pie data) |

## Data Sources (depends on P0-1~P0-4)

| Table | Source plugin | Key columns |
|-------|---------------|-------------|
| `crm_companies` | P0-1 | `id` / `name` / `tenant_id` |
| `crm_contacts` | P0-2 | `id` / `tenant_id` |
| `crm_opportunities` | P0-3 | `id` / `tenant_id` / `stage` / `status` / `estimated_amount` / `owner_id` / `company_id` / `created_at` / `updated_at` / `won_at` |
| `crm_quotations` | P0-4 | `id` / `tenant_id` / `status` / `final_amount` |

Stage order and labels are reused from P0-3 (`STAGE_DISPLAY_ORDER` /
`STAGE_LABELS`) to keep the dashboard funnel aligned with the opportunity
plugin's funnel chart.

## Key Design Decisions

1. **No new tables** — `models.py` is an empty placeholder (kept for future
   materialized view / cache table extensions)
2. **SQL-side aggregation for amounts** — every `sum()` uses
   `func.coalesce(func.sum(...), 0)` to avoid Python float drift
3. **Continuous month window** — the trend service synthesizes N consecutive
   month keys on the Python side and back-fills missing months with zeros
4. **Ranking excludes `owner_id IS NULL`** — un-owned opportunities are not
   attributed
5. **`win_rate` only considers terminal states** —
   `won_count / (won_count + lost_count)`; in-flight opportunities are
   excluded from the denominator
6. **LEFT JOIN for company name** — `company_name` is `None` when the related
   company is archived / deleted
7. **Tenant filtering** — every query carries an explicit `tenant_id` filter;
   `bypass_tenant_filter()` is used at the router layer to opt out of the
   global filter when needed

## Directory Layout

```
plugins/ddw_sales_dashboard/
├── __init__.py          # VERSION, PLUGIN_NAME
├── manifest.yaml        # Plugin metadata
├── plugin.py            # PluginBase subclass
├── models.py            # Empty placeholder (no new tables)
├── schemas.py           # 6 Pydantic response schemas
├── services.py          # DashboardService: 6 aggregation methods
├── router.py            # 7 API endpoints
├── tests/
│   ├── conftest.py      # Explicitly imports 4 upstream plugins' models
│   └── test_dashboard.py  # 7 tests
├── README.md
├── README_EN.md
└── LICENSE
```

## Dependencies

- `core.database.session` — `Base` / `session_scope` / `bypass_tenant_filter`
- `core.database.models` — `Base` / `TenantMixin` / `TimestampMixin`
- `sdk.plugin_base` — `PluginBase`
- `plugins.ddw_company_profile.models` — `Company`
- `plugins.ddw_contact_hub.models` — `Contact`
- `plugins.ddw_opportunity.models` — `Opportunity`
- `plugins.ddw_opportunity.services` — `STAGE_DISPLAY_ORDER` / `STAGE_LABELS`
- `plugins.ddw_quotation.models` — `Quotation`

## Tests

```bash
# Plugin only
python3 -m pytest plugins/ddw_sales_dashboard/tests/ -v

# Cross-plugin regression (P0-1~P0-4 + P0-5)
python3 -m pytest \
  plugins/ddw_company_profile/tests/ \
  plugins/ddw_contact_hub/tests/ \
  plugins/ddw_opportunity/tests/ \
  plugins/ddw_quotation/tests/ \
  plugins/ddw_sales_dashboard/tests/ -q
# Expected: 57 passed
```

## Version

- **v1.0.0** (2026-08-03) — initial release, 6 aggregation endpoints + 1
  health check
