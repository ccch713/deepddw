# Changelog

All notable changes to deepDDW are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-08-17

### Fixed

- **DEF-003** — `POST /api/v1/backup/restore` now returns **400** (client error) for invalid backup files (non-SQLite / failed integrity check) instead of 500; the live DB and the `.pre-restore` safety copy are never touched.
- **DEF-004** — `/api/v1/backup/create` no longer exposes the server's absolute path — only the filename is returned.
- **DEF-002** — `token_gate.py` docstring now matches behavior: LAN password-free is **off by default** (explicit opt-in via `DDW_LAN_BYPASS=1`).

### Changed

- **Reflection & consolidation (LLM polish)** — daily reflection follows a style guide (auto / professional / casual), enforces a progress / issues / tomorrow structure and avoids repeating the previous day; consolidation skips logging when the LLM judges the conversation valueless.
- **Memory search quality** — results are ranked by relevance score (hit-count × layer weight: user > notes > reflection > logs, plus freshness for recent logs) instead of insertion order; keyword-expansion cache expiry is tested.

## [0.2.0] - 2026-08-17

### Added — Multi-device on LAN (0.2.0)

- **Device identity & online registry** — each browser persists a `device_id` (localStorage) with a friendly name; reconnects keep the same identity; `/api/v1/status` shows online devices, active WebSockets, request counts, DB size and version.
- **Gateway rate limiting** — sliding window per Token + per IP (default 60 req/min/token, global cap → 503 overload protection), stdlib-only, configurable via `security.rate_limit.*` / `DDW_RATE_LIMIT_*` env.
- **SQLite concurrency hardening** — WAL + `busy_timeout=5000` + `synchronous=NORMAL` on every connection, plus a process-wide write lock for cross-table transactions (20 concurrent writers verified, no `database is locked`).
- **Workspace isolation (P1-1)** — devices pick a workspace (default `shared`); memory/logs and MCP memory tools are scoped per workspace, docs filtered by slug prefix; legacy clients unaffected.
- **Session resume across devices (P1-3)** — recent session summaries (up to 5) with a "continue" button; resume a conversation on another device.
- **Optional TLS (P1-2)** — one-command self-signed certificate (`scripts/gen_self_signed_cert.sh`, 1-year), enabled via `security.tls.*`; external access via Caddy/Nginx reverse proxy (see `docs/tls.md`).
- **Backup / restore API (P2-1)** — one-click backup via `POST /api/v1/backup/create`, downloadable; restore validates the SQLite file (header + integrity check) and keeps a `.pre-restore` safety copy before replacing the main DB.
- **Load-test tooling & report (P2-2)** — re-runnable async load script (`scripts/load_test/load_test.py`); measured 5/10/20 devices → 0% errors, P95 ≤ 126 ms, ~600 RPS, no `database is locked` (see `docs/load-report.md`).
- **Version / upgrade check (P2-3)** — `/api/v1/version` reports `latest_version` / `update_available` (GitHub releases, 1h cache, offline-degraded); launcher shows an upgrade banner.

### Changed

- Version bumped 0.1.0 → 0.2.0.

## [0.1.0] - 2026-08-16

### Added

- **Memory subsystem** — layered memory (user rules / project notes / daily logs / daily reflections + archive), automatic `<memory_system>` injection (budget-capped), LLM keyword expansion, AI distillation & daily reflection (graceful degradation).
- **Knowledge base** — hybrid vector + keyword retrieval (LanceDB + SQLite FTS5, RRF fusion; keyword-only fallback), automatic RAG (≤3 hits × 600 chars), session → document auto-ingest.
- **Deployment** — Docker one-click (`deepddw-compose.yml`), Windows standalone exe (PyInstaller via CI), `install.sh` one-command install.
- **Security** — Token gate (Bearer / `X-DDW-Token`, fail-fast), one-time 60s scan-to-pair codes, LAN bypass off by default, CORS tightening, cross-site WebSocket rejection.
- **CI** — pytest full suite + ruff (F/E9 zero-tolerance) on every push; windows-build workflow.
