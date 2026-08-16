# TLS / HTTPS — Optional

deepDDW runs on plain HTTP by default (LAN). TLS is **optional and off by default** —
enable it only when you need encryption on the wire or external access.

## Option A: Self-signed certificate (LAN HTTPS, one command)

```bash
# 1. Generate a 1-year self-signed cert for your host
./scripts/gen_self_signed_cert.sh data/tls localhost   # replace hostname as needed

# 2. Enable TLS in config/deployment.yaml
#    security:
#      tls:
#        enabled: true
#        cert_file: ./data/tls/cert.pem
#        key_file: ./data/tls/key.pem
#    (or env: DDW_TLS_ENABLED=true DDW_TLS_CERT=... DDW_TLS_KEY=...)

# 3. Restart — install.sh auto-detects and adds --ssl-certfile/--ssl-keyfile
./install.sh
```

Access `https://<host>:8500` — **first visit requires trusting the self-signed cert**
(accept the browser warning). Self-signed TLS is intended for trusted LANs only.

## Option B: Reverse proxy (recommended for external access)

Terminate TLS at a reverse proxy; deepDDW stays HTTP behind it. Set
`X-Forwarded-For` / `X-Forwarded-Proto` (see `trusted_proxies` in `deployment.yaml`).

**Caddy** (automatic HTTPS):

```caddyfile
deepddw.example.com {
    reverse_proxy 127.0.0.1:8500
}
```

**Nginx**:

```nginx
server {
    listen 443 ssl;
    server_name deepddw.example.com;
    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://127.0.0.1:8500;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        # WebSocket upgrade (DSH chat/events)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

> External access over plain HTTP is strongly discouraged — the gateway Token
> would travel in cleartext. Use Option B (or Option A + port-forward) for anything
> beyond your LAN.
