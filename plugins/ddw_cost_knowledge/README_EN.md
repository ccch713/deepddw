# DDW Cost Knowledge Base

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-1.0.0-green.svg)](manifest.yaml)
[![DDW](https://img.shields.io/badge/DDW-AI%20Hub-orange.svg)](#)

A unified repository for design-institute historical cost files, quotas, bills of quantities, and metrics — file upload, LLM extraction, natural-language search, history-driven cost estimation, and confidence scoring.

## Features

- **Cost File Upload**: Both metadata-only mode (just field entry) and binary mode (base64-encoded storage to disk) are supported
- **LLM Extraction**: Rule-based structured metric extraction (scale / unit price / cost tier / keywords), with an LLM hook routed through the DDW LLM Gateway for further enrichment
- **Natural-language Search**: Mixed Chinese/English scoring (English word tokens, Chinese 2-char bigrams), filterable by project type / document type
- **Cost Estimation**: Based on historical projects (weighted median + 25/75 percentiles + structure-type adjustment factor), with automatic confidence scoring (sample size + dispersion)
- **Statistics**: Total document count, distribution by file type / project type, average unit price / total cost
- **Batch Import**: Import multiple records from a single JSON list
- **Multi-tenant Support**: Data isolation by `tenant_id`

## Quick Start

### 1. Install

Copy the `ddw_cost_knowledge` directory into DDW AI Hub's `plugins/` directory.

### 2. Launch

DDW AI Hub automatically loads the plugin on startup. Registered at:

```
/api/v1/plugins/ddw-cost-knowledge/
```

### 3. API Examples

```bash
# Upload a cost file (metadata only)
curl -X POST http://localhost:8500/api/v1/plugins/ddw-cost-knowledge/documents/upload \
  -H "Content-Type: application/json" \
  -d '{
    "file_name": "Optics-Valley-A-Residential-2024.pdf",
    "doc_type": "Historical Cost File",
    "project_name": "Optics Valley A Residential",
    "project_type": "Residential",
    "area": 50000,
    "total_cost": 175000000
  }'

# Natural-language search
curl "http://localhost:8500/api/v1/plugins/ddw-cost-knowledge/search?q=residential%20frame%203500"

# Create a cost estimate
curl -X POST http://localhost:8500/api/v1/plugins/ddw-cost-knowledge/estimates \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "Optics Valley D New Residential",
    "project_type": "Residential",
    "area": 25000,
    "floor_count": 18,
    "structure_type": "Frame-Shear"
  }'

# Statistics overview
curl http://localhost:8500/api/v1/plugins/ddw-cost-knowledge/stats
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/documents/upload` | Upload cost file |
| GET | `/documents` | List files (pagination + filtering) |
| GET | `/documents/{id}` | File details |
| DELETE | `/documents/{id}` | Delete file (including disk file) |
| POST | `/documents/{id}/extract` | Trigger LLM extraction |
| GET | `/search` | Natural-language search |
| POST | `/estimates` | Create cost estimate |
| GET | `/estimates/{id}` | Estimate details |
| GET | `/stats` | Statistics overview |
| POST | `/batch-import` | Batch import (JSON list) |

## Data Model

| Table | Description |
|-------|-------------|
| `cost_documents` | Main cost file table (file name, type, project, area, total cost, unit price, LLM-extracted data, status) |
| `cost_estimates` | Cost estimate records (project type, area, floor count, structure type, estimate result, reference docs, confidence) |

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `upload_dir` | `./data/uploads/cost` | Directory for uploaded files |
| `default_tenant_id` | `1` | Default `tenant_id` in single-tenant mode |
| `estimate_similarity_threshold` | `0.6` | Historical project similarity threshold for estimation |
| `max_search_results` | `20` | Maximum number of search results |

## LLM Integration

This plugin's `extract` / `estimate` capabilities are routed through the **DDW LLM Gateway**, which is centrally managed by the DDW platform. All API keys, provider configs, and model selections are managed by the platform — **the plugin code does not contain any credentials**.

To enable LLM extraction, configure the LLM Gateway in `config/deployment.yaml`. No plugin code changes are required.

## Tech Stack

- Python 3.11+
- FastAPI
- SQLAlchemy 2.0 (async)
- SQLite / PostgreSQL
- pytest 8.0+

## Development & Testing

```bash
# Syntax check
python3 -c "import ast; ast.parse(open('router.py').read())"

# Run tests
python3 -m pytest tests/ -v

# Validate manifest
python3 -c "import yaml; yaml.safe_load(open('manifest.yaml'))"
```

## License

Apache License 2.0 — see [LICENSE](LICENSE)
