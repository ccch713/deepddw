# DDW SearXNG Plugin

Wraps SearXNG (MIT meta search engine) JSON API as a DDW standard plugin.

## Features

- **Search**: `GET /api/v1/plugins/ddw-searxng/search?q=keyword&limit=5`
- **Health check**: `GET /api/v1/plugins/ddw-searxng/health`

## Configuration

| Env Variable | Default | Description |
|:--|:--|:--|
| `SEARXNG_URL` | `http://127.0.0.1:8888` | SearXNG service URL |

## API Examples

```bash
# Search
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8500/api/v1/plugins/ddw-searxng/search?q=AI&limit=5"

# Health check
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8500/api/v1/plugins/ddw-searxng/health"
```

## Authentication

All endpoints require `Authorization: Bearer <jwt>` (DDW user role).

## Error Handling

When SearXNG is unreachable, search returns:
```json
{"success": false, "error": "SEARXNG_UNREACHABLE", "detail": "..."}
```

Health endpoint always returns 200, using `ok` field to indicate status.
