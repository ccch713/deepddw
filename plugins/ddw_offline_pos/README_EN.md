# DDW Payment Plugin (ddw-payment v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P1-4** — Sales-side received-payment ledger.

## Description

- **Master Table + Auto Numbering**: `PAY-YYYYMMDD-NNN`
- **Status Machine**: `pending` (awaiting reconcile) → `matched` (fully reconciled) / `partial` (partially) / `unmatched` (no match)
- **Multi-dim Filter**: by company / payer / payment method / status / date
- **Statistics Overview**: total / pending / matched / partial / unmatched + by_payment_method
- **Unmatched List**: separate endpoint for the finance team to action
- **Reconciliation is Handled by P1-5**: this plugin only records received payments + status queries
- **Multi-tenant Isolation**: data isolation by `tenant_id`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /payments | Create payment (auto payment_no) |
| GET | /payments | List (paginated + multi-dim filter) |
| GET | /payments/stats | Statistics |
| GET | /payments/unmatched | Unmatched list |
| GET | /payments/{id} | Payment details |
| PUT | /payments/{id} | Update payment |

## Data Model

`Payment` table (`crm_offline_pos_records`) core fields:

- **PK**: `id` (BigInt)
- **Number**: `payment_no` (unique, PAY-YYYYMMDD-NNN)
- **Tenant**: `tenant_id` (from `TenantMixin`)
- **Link**: `company_id` (FK → crm_companies.id, ON DELETE CASCADE)
- **Payer**: `payer_name` (full payer company name) / `bank_reference` (bank流水号)
- **Amount**: `amount` (Numeric(12,2)) / `matched_amount` (Numeric(12,2), default 0)
- **Time**: `payment_date` (Date)
- **Method**: `payment_method` (bank/cheque/cash/wechat/alipay)
- **Account**: `bank_account` (收款账户)
- **Status**: `status` (pending/matched/partial/unmatched)
- **Audit**: `created_at` / `updated_at` (from `TimestampMixin`)

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| default_page_size | int | 20 | Default page size |
| statuses | array | [pending, matched, partial, unmatched] | Status enum |
| payment_methods | array | [bank, cheque, cash, wechat, alipay] | Payment method enum |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_offline_pos/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.models.TimestampMixin` — timestamps
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter
- `sdk.plugin_base.PluginBase` — plugin base class
- `plugins.ddw_company_profile` — soft dependency

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
