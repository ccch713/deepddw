# DDW Lead Claim Plugin (ddw-lead-claim v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P2-2** — Lead registration, protection period, conflict arbitration, release.

## Description

- **Lead Registration**: Channel partners register leads for target customers, with `expire_at = claim_date + protection_days` auto-calculated
- **Protection Period**: Default 60 days, no duplicate active claims by same partner for same company
- **Conflict Arbitration**: Multi-channel claims resolved by "first claim + last 30 days follow-up evidence"
- **Auto-expire**: `status='expired'` set by `_auto_mark_expired()` before list/get
- **Manual Release**: `/release` endpoint
- **Multi-tenant Isolation**: data isolation by `tenant_id`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /claims | Create claim (auto-calculate expire_at) |
| GET | /claims | List claims (paginated + filter) |
| GET | /claims/{id} | Claim details |
| PUT | /claims/{id} | Update (active only) |
| POST | /claims/{id}/release | Manual release |
| GET | /claims/conflict | Conflict query (input: company_id) |
| GET | /claims/stats | Statistics |

## Business Rules

1. **Same partner can have at most 1 active claim per company** (anti-duplicate-occupy)
2. **expire_at = claim_date + protection_days** (server-side, ignore client input)
3. **Auto-expire on protection timeout** (batch update before list/stats)
4. **After release: status=released** (record release_reason)

## Data Model

`LeadClaim` table (`crm_lead_claims`):

- **PK**: `id` (BigInt)
- **Tenant**: `tenant_id`
- **References**: `partner_id` (FK) / `company_id` (FK)
- **Claim**: `claim_date` / `protection_days` / `expire_at`
- **Contact**: `contact_person` / `contact_phone` / `opportunity_source`
- **Business**: `expected_amount` / `follow_up_notes` / `last_follow_up_at`
- **Status**: `status` (active/expired/won/lost/released)
- **Audit**: `created_at` / `updated_at`

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_lead_claim/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base`
- `core.database.models.TenantMixin` / `TimestampMixin`
- `sdk.plugin_base.PluginBase`

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
