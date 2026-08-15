# ddw_ai_readiness Plugin

Enterprise AI Readiness Self-Assessment plugin for receiving questionnaire answers, server-side scoring, business opportunity grading (A/B/C), SQLite storage, and sales-side query/statistics.

## Features

- Receive frontend questionnaire answers (anonymous submission allowed)
- Server-side scoring (tamper-proof)
- Business opportunity grading (A/B/C levels)
- SQLite auto-creation, zero configuration
- Sales-side query and statistics

## API Endpoints

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/api/v1/plugins/ddw_ai_readiness/submissions` | Submit assessment | Anonymous |
| GET | `/api/v1/plugins/ddw_ai_readiness/submissions` | Sales list | Login required |
| GET | `/api/v1/plugins/ddw_ai_readiness/submissions/{sid}` | Sales detail | Login required |
| GET | `/api/v1/plugins/ddw_ai_readiness/stats` | Statistics | Anonymous |
| GET | `/api/v1/plugins/ddw_ai_readiness/health` | Health check | Anonymous |

## Deployment

SQLite auto-creation, zero configuration. Database file located at `plugins/ddw_ai_readiness/data/readiness.db`.

## Frontend Entry

Frontend HTML file located at `商务物料/DDW-就绪度自评/ddw-ai-readiness.html`, configure `API_BASE` to point to backend address.

## Production Deployment

Recommended to add access control for sales-side endpoints (list/detail) via Caddy/gateway layer.