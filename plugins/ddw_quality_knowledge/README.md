# DDW Quality Knowledge Plugin

Intelligent knowledge retrieval for food safety management.

## Features
- **Standards Knowledge**: ISO 22000, FSSC 22000, HACCP, GMP
- **SOP Management**: Standard operating procedures retrieval
- **Regulatory Index**: NHC, EU Novel Food, EFSA regulations
- **Case Library**: Historical quality cases and solutions
- **Semantic Search**: LLM-powered relevance ranking
- **Pre-built Data**: Seed with core food safety standards

## API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| POST | `/documents` | Create document |
| GET | `/documents` | List documents |
| GET | `/documents/{id}` | Get document |
| PUT | `/documents/{id}` | Update document |
| DELETE | `/documents/{id}` | Delete document |
| POST | `/search` | Keyword search |
| POST | `/search/semantic` | Semantic search |
| POST | `/seed` | Seed core standards |
| GET | `/stats` | Search analytics |
| GET | `/health` | Health check |

## License
Apache-2.0
