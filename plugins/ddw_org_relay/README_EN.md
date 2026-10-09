# ddw-org-relay · Organization Binding Plugin (bindcode-v1 server)

Turns this deepDDW instance into an **organization backend** that DDW AI Assistant
apps can bind to (open protocol
[bindcode-v1](../../docs/组织连接协议-bindcode-v1.md)). **Off by default**;
enable via config.

```text
Staff app ──bind code──▶ ┌────────── this deepDDW instance ──────────┐
                         │ pub trio (product token + rate limit):   │
                         │ bind / unbind / me                       │
                         │ member access_token → chat/completions   │──▶ llm_gateway
                         │ admin/* (instance token, keep private)   │    (deployer-configured)
                         └──────────────────────────────────────────┘
```

## Enable

In `config/deployment.yaml`:

```yaml
org_relay:
  enabled: true
  product_tokens:            # product tokens (multi; held by the app's product side)
    - "a-very-long-random-product-token"
  server_base_url: ""        # this instance's LLM endpoint base; set explicitly for
                             # public deployments (no built-in external default)
  rate_limit_per_token: 10   # 10 req/min per product token (protocol §6)
  bindcode_ttl_min: 15
  bindcode_max_uses: 50
```

Or via env: `DDW_ORG_RELAY_ENABLED=1`, `DDW_ORG_RELAY_PRODUCT_TOKENS=tok1,tok2`,
`DDW_ORG_RELAY_SERVER_BASE_URL=...` (env takes precedence).

## Workflow

1. **Admin issues a bind code** (instance static token, i.e. `DDW_ACCESS_TOKEN`):

   ```bash
   # create an org (org_secret is returned exactly once; rotate if lost)
   curl -X POST :8500/api/v1/plugins/ddw-org-relay/admin/orgs \
        -H "Authorization: Bearer $DDW_ACCESS_TOKEN" \
        -H 'Content-Type: application/json' -d '{"name":"Acme Clinic","plan":"light"}'
   # issue bind codes (default: 15 min / 50 uses)
   curl -X POST :8500/api/v1/plugins/ddw-org-relay/admin/orgs/<org_id>/bindcode \
        -H "Authorization: Bearer $DDW_ACCESS_TOKEN" \
        -H 'Content-Type: application/json' -d '{"ttl_min":15,"max_uses":50}'
   ```

2. **Staff app scans / pastes the code** (product side calls the public trio with
   the Bearer product token):

   - `POST /api/v1/relay/org/pub/bind` `{user_id, code}` → `{bound, org}`
   - `POST /api/v1/relay/org/pub/unbind` `{user_id}` → `{bound: false}`
   - `GET  /api/v1/relay/org/pub/me?user_id=...` → `{bound, org, org_consumed_total}`

   The `org` object includes the protocol §3.1 optional fields:
   `server_base_url` (this instance's LLM endpoint), `access_token`
   (member-level credential, invalidated on unbind/revoke), `models`
   (deployer-configured model list).

3. **Members call this instance's LLM endpoint directly** (OpenAI-compatible):

   ```bash
   curl -X POST <server_base_url>/chat/completions \
        -H "Authorization: Bearer <org.access_token>" \
        -H 'Content-Type: application/json' \
        -d '{"messages":[{"role":"user","content":"hi"}]}'
   ```

## Product boundaries (as implemented)

- **LLM supply is fully deployer-configured**: `chat/completions` is backed by
  this instance's `llm_gateway` provider config (DeepSeek / Ollama / any
  self-hosted OpenAI-compatible gateway, see `/api/v1/llm/config`). The plugin
  ships no built-in and no preset external model channel.
- **Binding is not backend lock-in**: `unbind` only ends the relation and
  invalidates the member token; the app-side personal mode and local data are
  untouched (protocol §4). The server holds no staff personal data and deletes
  nothing on unbind (usage rows are metadata-only and retained for accounting).

## Security notes (protocol §6)

| Item | Implementation |
| --- | --- |
| org_secret | ≥32 random bytes, encrypted at rest (Fernet); rotation supported (old codes stay valid until expiry); never appears in any response |
| Verification | HMAC-SHA256 first 16 hex chars, constant-time `hmac.compare_digest` |
| Public rate limit | 10 req/min per product token (sliding window, 429 + Retry-After) |
| Admin endpoints | Gated by the instance static token; **do not expose publicly** (firewall / reverse proxy should only allow `/api/v1/relay/org/pub/*` and `chat/completions`) |
| Logs / usage rows | Metadata only (org_id / user_id / action / model / token counts) — never request bodies |
| Storage | Dedicated database `data/org_relay.db`; no user accounts or roles — bindings only |

## Endpoints

| Endpoint | Auth | Notes |
| --- | --- | --- |
| `POST /api/v1/relay/org/pub/bind` | product token | bind (403 forged / 410 expired / 409 exhausted or bound elsewhere / 404 revoked) |
| `POST /api/v1/relay/org/pub/unbind` | product token | unbind (idempotent) |
| `GET /api/v1/relay/org/pub/me` | product token | org state query |
| `POST /api/v1/plugins/ddw-org-relay/chat/completions` | member access_token | OpenAI-compatible chat (stream supported); per-org request quota optional |
| `.../admin/orgs` (GET/POST) + sub-resources | instance token | create/detail/issue/revoke/rotate/disable/quota/unbind/usage |
| `GET .../health` | none | `{"protocol":"bindcode","protocol_version":"1"}` (protocol §7) |

Tests: `pytest plugins/ddw_org_relay/tests/ -q` (47 cases: code issue/verify units
plus the full endpoint matrix).
