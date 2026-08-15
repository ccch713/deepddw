# DDW Sales Note Plugin (ddw-sales-note v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P3-2** — Visit, call, meeting, email, WeChat communication notes.

## Description

- **Note Types**: visit / call / meeting / email / wechat
- **Content**: title + content (required)
- **Timing**: visit_date (occurrence time)
- **Business Associations**: user_id (recorder) / company_id / contact_id / opportunity_id
- **Tags**: JSON list
- **Attachments**: JSON list of URLs
- **By Opportunity Query**: /notes/by-opportunity/{opportunity_id}
- **Date Range Filter**: visit_date range
- **Recent 30d Statistics**: `recent_30d` field
- **Hard Delete**: DELETE is physical (different from soft-delete in other plugins)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /notes | Create note |
| GET | /notes | List (paginated + filter) |
| GET | /notes/by-opportunity/{opportunity_id} | Notes by opportunity |
| GET | /notes/{id} | Details |
| PUT | /notes/{id} | Update |
| DELETE | /notes/{id} | **Hard delete** |
| GET | /notes/stats | Statistics (incl. recent_30d) |

## Data Model

`SalesNote` table (`crm_sales_notes`):

- **PK**: `id`
- **Tenant**: `tenant_id`
- **Recorder**: `user_id`
- **References**: `company_id` / `contact_id` / `opportunity_id`
- **Type**: `note_type` (visit/call/meeting/email/wechat)
- **Content**: `title` / `content` (Text, NOT NULL)
- **Timing**: `visit_date` (DateTime, index)
- **Extended**: `tags` (JSON list) / `attachments` (JSON list)

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_sales_note/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base`
- `core.database.models.TenantMixin` / `TimestampMixin`
- `sdk.plugin_base.PluginBase`

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
