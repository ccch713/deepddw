# DDW Transcript AI Plugin (ddw-transcript-ai v1.0.0)

DDW AI Hub Sales CRM Plugin Suite **P3-3** — AI processing for sales-side audio recordings / text. Backed by the DDW built-in LLM Gateway.

## Description

- **Transcribe**: simulated ASR (returns text from a URL or pre-uploaded audio reference)
- **Summarize**: text summarization
- **Extract Todos**: action item extraction
- **Extract Entities**: key entity extraction (company names, people, products, amounts, dates, etc.)
- **No persistence**: pure aggregation AI capability (no DB table)
- **All LLM Calls via Gateway**: only `llm.invoke` permission, no provider details exposed
- **Multi-tenant Aware**: requests carry `tenant_id`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /health | Health check |
| POST | /transcript/transcribe | Transcribe (audio URL → text) |
| POST | /transcript/summarize | Text summarization |
| POST | /transcript/extract-todos | Extract action items |
| POST | /transcript/extract-entities | Extract key entities |

## Data Model

**No table**, pure aggregation API.

## Installation

Shipped with the DDW AI Hub platform. No separate install needed.

## Configuration

`manifest.yaml` `config_schema` section:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_tenant_id | int | 1 | Default tenant |
| default_language | string | zh-CN | Default transcription language |
| default_summary_max_length | int | 200 | Default summary max length (chars) |
| max_input_length | int | 32000 | Max request text length (chars; 400 on overflow) |

## Testing

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_transcript_ai/tests/ -v --tb=short
```

## Dependencies

- `core.database.session.Base` — ORM root
- `core.database.models.TenantMixin` — multi-tenancy
- `sdk.plugin_base.PluginBase` — plugin base class
- DDW LLM Gateway (embedded_llm)

## License

Apache License 2.0 — Wuhan Ruiguo Interactive Information Technology Co., Ltd.
