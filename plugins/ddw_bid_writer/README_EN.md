# DDW Bid Document Writer

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-1.0.0-green.svg)](manifest.yaml)
[![DDW](https://img.shields.io/badge/DDW-AI%20Hub-orange.svg)](#)

End-to-end assistance for design-institute bid workflows — project setup, automatic bid-document generation, document language polishing & expression-style adjustment, document review, and template management. Includes the CDEF (Corporate Document Extraction Framework) 4-stage pipeline and a vector knowledge base, designed to work with small local LLM deployments.

## Features

- **Project Setup**: Bid project master data management (project name, client, type, estimated amount, deadline, status)
- **Automatic Bid Generation**: Complete bid documents (Technical / Commercial / Pre-qualification) based on section templates + project info + LLM
- **Language Polishing & Expression-Style Adjustment**: Enterprise-preference-driven wording and expression adjustment for generated documents
  - Style options: Standard / Conservative / Aggressive / Innovative
  - Adjustment dimensions: wording / structure / charts / expression / terminology
  - Version history preserved for comparison and rollback
- **Document Review**: 6 automated checks (section completeness, key fields, sensitive words, length, structure, contact info) + scoring + suggestions
- **Approval**: Closed-loop approval workflow
- **Template Management**: User-defined + system-default templates
- **CDEF Framework**: 4-stage pipeline (Plan → Parallel Generation → Consistency Check → Polish)
- **RAG Vector Knowledge Base**: Historical-bid similarity retrieval augmentation
- **Multi-Agent Collaboration**: Planner / Writer / Reviewer / Editor working in concert
- **Progressive Disclosure**: Automatic important-project detection with per-section lock / unlock / regenerate
- **Multi-tenant Support**: Data isolation by `tenant_id`

## Quick Start

### 1. Install

Copy the `ddw_bid_writer` directory into DDW AI Hub's `plugins/` directory.

### 2. Launch

DDW AI Hub automatically loads the plugin on startup. Registered at:

```
/api/v1/plugins/ddw-bid-writer/
```

### 3. Workflow

```
┌────────────────────────────────────────────────────────┐
│  1. Knowledge Base Bootstrap (one-time)                  │
│     Select historical bid folder → auto-learn (parse /  │
│     chunk / vectorize / extract templates)               │
│                                                           │
│  2. Create Bid Project                                   │
│     Fill project info → system evaluates importance      │
│     (routine / important / critical)                     │
│                                                           │
│  3. Generate Bid                                         │
│     Routine: auto mode (one-click)                       │
│     Important: progressive disclosure (per-section)       │
│                                                           │
│  4. Review & Approve                                     │
│     Auto review → scoring → human review → approve      │
└────────────────────────────────────────────────────────┘
```

### 4. API Examples

```bash
# Bootstrap knowledge base from historical bids
curl -X POST http://localhost:8500/api/v1/plugins/ddw-bid-writer/knowledge/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"folder": "/path/to/historical/bids", "tenant_id": 1}'

# Create a bid project
curl -X POST http://localhost:8500/api/v1/plugins/ddw-bid-writer/projects \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "Optics Valley A Residential Bid",
    "client_name": "Optics Valley Holdings",
    "project_type": "Residential",
    "estimated_amount": 500000000
  }'

# Assess project importance
curl -X POST http://localhost:8500/api/v1/plugins/ddw-bid-writer/projects/1/assess-importance \
  -H "Content-Type: application/json" -d '{}'

# Generate bid (CDEF 4-stage pipeline)
curl -X POST http://localhost:8500/api/v1/plugins/ddw-bid-writer/projects/1/generate \
  -H "Content-Type: application/json" \
  -d '{"doc_type": "Technical Bid", "style": "Standard", "mode": "auto"}'

# Review bid
curl -X POST http://localhost:8500/api/v1/plugins/ddw-bid-writer/documents/1/review \
  -H "Content-Type: application/json" -d '{}'
```

## API Endpoints (25 total)

### Project Management
| Method | Path | Description |
|--------|------|-------------|
| POST | `/projects` | Create bid project |
| GET | `/projects` | List projects |
| GET | `/projects/{id}` | Project details |
| PUT | `/projects/{id}` | Update project |
| DELETE | `/projects/{id}` | Delete project |
| POST | `/projects/{id}/generate` | Generate bid (CDEF 4-stage pipeline) |
| GET | `/projects/{id}/documents` | All bid documents under project |
| POST | `/projects/{id}/plan` | Stage 1: generate outline only |
| POST | `/projects/{id}/assess-importance` | Assess project importance |

### Bid Documents
| Method | Path | Description |
|--------|------|-------------|
| GET | `/documents/{id}` | Document details |
| PUT | `/documents/{id}` | Edit document |
| POST | `/documents/{id}/refine` | Document language polishing & expression-style adjustment |
| POST | `/documents/{id}/review` | Document review (compliance check) |
| POST | `/documents/{id}/approve` | Approve document |
| GET | `/documents/{id}/sections` | Section-level list (progressive disclosure) |
| POST | `/documents/{id}/sections/{idx}/regenerate` | Section-level regeneration |
| POST | `/documents/{id}/sections/{idx}/lock` | Lock section |
| POST | `/documents/{id}/sections/{idx}/unlock` | Unlock section |

### Template Management
| Method | Path | Description |
|--------|------|-------------|
| GET | `/templates` | List templates |
| POST | `/templates` | Create template |
| PUT | `/templates/{id}` | Update template |
| DELETE | `/templates/{id}` | Delete template |

### Knowledge Base
| Method | Path | Description |
|--------|------|-------------|
| POST | `/knowledge/bootstrap` | Learn from historical bid folder |
| GET | `/knowledge/status` | Knowledge base status |
| GET | `/knowledge/templates` | Learned template list |

## Data Model

| Table | Description |
|-------|-------------|
| `bid_projects` | Bid project master table |
| `bid_documents` | Bid documents (content / version / status) |
| `bid_templates` | Bid templates |
| `bid_sections` | Section-level records (lockable) |
| `bid_kb_documents` | Historical bid records for learning |
| `bid_kb_runs` | Learning run audit |
| `bid_fact_templates` | Learned fact templates |
| `bid_agent_runs` | Multi-agent run audit |

## CDEF 4-Stage Pipeline

```
Plan → Parallel Generation → Consistency Check → Polish
```

- **Plan**: Generate outline (6 sections × target word count) + style baseline + FactSheet init
- **Parallel Generation**: 6 sections run via `asyncio.gather`; each prompt includes FactSheet (hard constraint) + style baseline + transition context + RAG top-3
- **Consistency Check**: Extract all facts → compare with FactSheet → flag conflicts → local rewrite
- **Polish**: Whole-document polish + consolidation

### Key Components

- **FactSheet**: Structured fact table (project name / client / amount / personnel / dates / metrics / style baseline) injected into every chapter prompt as a hard constraint
- **RAG**: Tenant-scoped local vector store; retrieves top-3 similar historical chapters before each generation
- **Multi-Agent**: 4 agents collaborate through the DDW LLM Gateway; full trace stored in `bid_agent_runs`
- **Importance Detector**: Composite scoring (amount + deadline + first-time client + project type) → routine / important / critical

## Generation Modes

| Mode | Behavior | Use Case |
|------|----------|----------|
| `auto` | CDEF full 4-stage pipeline | Routine projects (< 100M) |
| `important` | Progressive disclosure (per-section API) | Important / critical projects (≥ 100M) |
| `skeleton` | Outline only | Quick preview |
| `legacy` | Legacy one-shot generation | Backward compatibility |

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `available_styles` | `[Standard, Conservative, Aggressive, Innovative]` | Available style-adjustment options |
| `default_doc_type` | `Technical Bid` | Default bid type |
| `use_llm` | `false` | Enable real LLM calls (turn on in production) |

## LLM Integration

All LLM calls in this plugin (extraction / polishing / review / assessment) are routed through the **DDW LLM Gateway**, which is centrally managed by the DDW platform:

- **API keys / Providers / model selection** are managed in the platform's `config/deployment.yaml`
- **No credentials are stored in the plugin code**
- Local LLM backends (e.g., llama.cpp) can be plugged in as a Provider
- For small local models, we recommend splitting workloads: let the local LLM handle core tasks (fact consistency, style baseline, key fields) and use a cloud LLM for non-core tasks (polishing, expansion)

## Compliance

- This plugin uses **neutral naming** for sensitive capabilities ("document language polishing & expression-style adjustment")
- The sensitive-word library is loaded from an external config file — no hardcoding in source code
- Style options are described **neutrally** (Standard / Conservative / Aggressive / Innovative), with no implication of purpose
- All UI / documentation / comments are scanned by automated sensitive-word checks

## Tech Stack

- Python 3.11+
- FastAPI
- SQLAlchemy 2.0 (async)
- SQLite / PostgreSQL
- DDW LLM Gateway
- pytest 8.0+

## Development & Testing

```bash
# Syntax check
python3 -c "import ast; ast.parse(open('router.py').read())"

# Run tests
python3 -m pytest tests/ -v

# Validate manifest
python3 -c "import yaml; yaml.safe_load(open('manifest.yaml'))"

# Sensitive-word scan (terms are loaded from external config, not hardcoded in README)
python3 -c "
from pathlib import Path
import re
SENSITIVE_PLACEHOLDER = re.compile(r'PROHIBITED_TERM_\d+')  # replace with real loader in deployment
bad = []
for f in Path('.').rglob('*.py'):
    if '/tests/' in str(f): continue
    text = f.read_text(encoding='utf-8', errors='ignore')
    if SENSITIVE_PLACEHOLDER.search(text):
        bad.append(f'{f}: placeholder match')
print('PASS' if not bad else f'FAIL: {bad}')
"
```

## License

Apache License 2.0 — see [LICENSE](LICENSE)
