# DDW Voice Capture Plugin (ddw-voice-capture v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P3-1** — Voice record metadata management.

## Description

- **Metadata Upload**: file_url + file_size + duration_seconds + source_type
- **Source Classification**: local / phone / meeting / memo
- **Business Associations**: user_id / company_id / contact_id / opportunity_id
- **Status Machine**: uploaded → transcribed → processed / failed
- **Soft Delete**: DELETE marks status=failed (audit retained)
- **Multi-tenant Isolation**

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /voice-records | Upload voice record metadata |
| GET | /voice-records | List (paginated + filter) |
| GET | /voice-records/{id} | Details |
| DELETE | /voice-records/{id} | Soft delete (status=failed) |
| GET | /voice-records/stats | Statistics |

## Data Model

`VoiceRecord` table (`crm_voice_records`):

- **PK**: `id`
- **Tenant**: `tenant_id`
- **Uploader**: `user_id` / `created_by`
- **References**: `company_id` / `contact_id` / `opportunity_id`
- **File**: `file_url` / `file_size` / `duration_seconds`
- **Source**: `source_type`
- **Status**: `status` (uploaded/transcribed/processed/failed)
- **Notes**: `notes`

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_voice_capture/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base`
- `core.database.models.TenantMixin` / `TimestampMixin`
- `sdk.plugin_base.PluginBase`

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
