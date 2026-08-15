# DDW Personnel Qualification Management

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-1.0.0-green.svg)](manifest.yaml)
[![DDW](https://img.shields.io/badge/DDW-AI%20Hub-orange.svg)](#)

A full-lifecycle certificate management plugin for design institute staff — entry, query, batch import/export, expiry alerts, renewal tracking, and statistics overview.

## Features

- **Certificate Ledger**: Supports all certificate types including Registered Architect, Registered Structural Engineer, Registered Equipment Engineer, Supervision Engineer, Cost Engineer, Consulting Engineer, and Class-1 Constructor
- **Batch Import / Export**: CSV / Excel batch import, CSV export
- **Smart Expiry Alerts**: Tiered warnings at 30 / 60 / 90 days, with configurable lead time
- **Renewal Tracking**: Full lifecycle management of annual renewals (initiate → pass / fail → auto-sync certificate status)
- **Statistics Overview**: One-glance view of total / active / expired / renewing counts and type / level distribution
- **Multi-tenant Support**: Data isolation by `tenant_id`, integrated with the DDW platform's tenant management

## Quick Start

### 1. Install

Copy the `ddw_personnel_qual` directory into DDW AI Hub's `plugins/` directory.

### 2. Launch

DDW AI Hub automatically scans the `plugins/` directory and loads this plugin on startup. The plugin is registered at:

```
/api/v1/plugins/ddw-personnel-qual/
```

### 3. API Examples

```bash
# Create a certificate
curl -X POST http://localhost:8500/api/v1/plugins/ddw-personnel-qual/certs \
  -H "Content-Type: application/json" \
  -d '{
    "person_name": "Zhang San",
    "person_id": "ZS001",
    "cert_type": "Class-1 Registered Structural Engineer",
    "cert_no": "S20240001",
    "cert_level": "Class-1",
    "expiry_date": "2027-12-31"
  }'

# Query expiring certificates (30/60/90 day buckets)
curl http://localhost:8500/api/v1/plugins/ddw-personnel-qual/expiring

# Statistics overview
curl http://localhost:8500/api/v1/plugins/ddw-personnel-qual/stats
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/certs` | Create certificate |
| GET | `/certs` | List certificates (pagination + filtering) |
| GET | `/certs/{id}` | Certificate details |
| PUT | `/certs/{id}` | Update certificate |
| DELETE | `/certs/{id}` | Delete certificate |
| POST | `/certs/import` | Batch import (CSV / Excel) |
| GET | `/certs/export` | Export CSV |
| GET | `/expiring` | Expiry alert list (30/60/90 day buckets) |
| GET | `/stats` | Statistics overview |
| GET | `/persons/{id}/certs` | All certificates for one person |
| POST | `/renewals` | Initiate annual renewal |
| PUT | `/renewals/{id}` | Update renewal status |
| GET | `/renewals` | List renewal records |
| GET | `/alerts` | List alert notifications |

## Data Model

| Table | Description |
|-------|-------------|
| `personnel_certs` | Main certificate table (person, type, number, level, issue/expiry/renewal dates, status) |
| `cert_renewals` | Annual renewal records (linked to cert_id, date, result, operator) |
| `cert_alerts` | Alert notifications (tiered by expiry: 30/60/90 days) |

All tenant-scoped tables inherit from `TenantMixin`; DDW platform auto-filters by `tenant_id`.

## Configuration

| Key | Default | Description |
|-----|---------|-------------|
| `expiry_warn_days` | `90` | Lead time (days) for expiry alerts (30/60/90 tiered) |
| `default_tenant_id` | `1` | Default `tenant_id` in single-tenant mode |

Configure via DDW AI Hub's `config/deployment.yaml` or admin console.

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
