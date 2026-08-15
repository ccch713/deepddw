# DDW Quality Assistant Plugin

AI-powered quality document generation for food/biotech manufacturing.

## Features
- **8D Report Generation**: Complete 8D problem-solving report drafts
- **CAPA Draft**: Corrective and preventive action document generation
- **Deviation Report**: Deviation investigation report drafts
- **Complaint Reply**: Professional customer complaint reply generation
- **5-Why Analysis**: Structured root cause analysis with 5-Why method

## API Endpoints
| Method | Path | Description |
|--------|------|-------------|
| POST | `/8d` | Generate 8D report |
| POST | `/capa` | Generate CAPA draft |
| POST | `/deviation` | Generate deviation report |
| POST | `/complaint-reply` | Generate complaint reply |
| POST | `/5why` | Perform 5-Why analysis |
| GET | `/documents` | List documents |
| GET | `/documents/{id}` | Get document |
| PATCH | `/documents/{id}/status` | Update status |
| GET | `/5why` | List 5-Why analyses |
| GET | `/health` | Health check |

## License
Apache-2.0
