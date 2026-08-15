# DDW Support Ticket Plugin (ddw-support-ticket v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P4-5** — Full lifecycle management of customer support tickets (bug reports, questions, complaints, feature requests).

## Description

- **Auto-generated Ticket No**: `TKT-YYYYMMDD-NNN` (NNN is daily sequence, starting from 001)
- **Categories**: `bug` / `feature` / `question` / `complaint` / `other`
- **Priority**: `low` / `normal` / `high` / `urgent`
- **Status Machine**: `open` → `in_progress` → `resolved` → `closed` (can jump from open/in_progress to closed)
- **Assignee**: `assigned_to` (user ID) + status machine coupling
- **Resolution**: `resolution` text field for handler conclusion
- **Multi-dim Filter**: by company / instance / category / priority / status / assignee
- **Multi-tenant Isolation**: data isolation by `tenant_id`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /tickets | Create ticket (auto-generate ticket_no) |
| GET | /tickets | List (paginated + multi-dim filter) |
| GET | /tickets/stats | Statistics |
| GET | /tickets/{id} | Ticket details |
| PUT | /tickets/{id} | Update ticket |
| POST | /tickets/{id}/assign | Assign handler (open → in_progress) |
| POST | /tickets/{id}/start | Start processing (open → in_progress) |
| POST | /tickets/{id}/resolve | Resolve (in_progress → resolved) |
| POST | /tickets/{id}/close | Close (resolved → closed) |

## Data Model

`SupportTicket` table (`crm_support_tickets`) core fields:

- **PK**: `id` (BigInt)
- **Ticket No**: `ticket_no` (unique, TKT-YYYYMMDD-NNN)
- **Tenant**: `tenant_id` (from `TenantMixin`)
- **Links**: `company_id` (FK → crm_companies.id, ON DELETE CASCADE) / `instance_id` (FK → crm_instances.id, nullable)
- **Info**: `title` / `description` / `category` / `priority`
- **Handling**: `assigned_to` (user ID) / `resolution` / `resolved_at`
- **Status**: `status` (open/in_progress/resolved/closed)
- **Audit**: `created_at` / `updated_at` (from `TimestampMixin`)

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| default_page_size | int | 20 | Default page size |
| categories | array | [bug, feature, question, complaint, other] | Category enum |
| priorities | array | [low, normal, high, urgent] | Priority enum |
| statuses | array | [open, in_progress, resolved, closed] | Status enum |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_support_ticket/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `core.database.models.TimestampMixin` — timestamps
- `core.database.tenant_filter.bypass_tenant_filter` — bypass tenant filter
- `sdk.plugin_base.PluginBase` — plugin base class
- `plugins.ddw_company_profile` / `plugins.ddw_instance_binding` — soft dependencies

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
