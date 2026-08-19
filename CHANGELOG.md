# Changelog

All notable changes to deepDDW are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-08-18

> **"DSH for Teams" 架构重写 — 深度重构为 DSH 原生插件，实现多用户记忆/知识库隔离。**
> 📌 **Listed in [awesome-deepseek-harness](https://github.com/0xsline/awesome-deepseek-harness#memory--knowledge)** (500+ stars DSH 生态导航，Memory & Knowledge 板块唯一多设备/团队方案)。

### Changed — 架构重写

- **纯 DSH Cordis 插件** — 删除独立 Launcher 页面，deepDDW 完全嵌入 DSH 作为原生插件；通过 DSH 设置面板「设置 → 多用户设置」管理，100% DSH 原生 UI（`--dsw-alias-*` 语义 Token，零自定义 CSS）
- **首次使用引导** — 首次打开 DSH 弹出「选择使用模式」：一人多设备（8GB 内存）/ 家庭多人（16GB，5 人以下）/ 小团队协作（32GB+，20 人以内）
- **成员管理三页签** — 活跃成员（🟢/⚪在线状态）/ 已吊销（可多选提取记忆到团队共享空间）/ 已删除
- **成员识别安全模式** — 手动输入成员名称验证绑定（非列表选择，防冒充）
- **设备心跳注册** — 每次页面加载自动注册设备心跳，确保在线状态实时准确
- **客户端构建管线** — 引入 tsdown，TypeScript 源码 → `__ModuleLoader__` 格式客户端 bundle
- **成员记忆提取** — 新增 `POST /api/v1/member/extract`（多选 → 提取到团队共享空间 → 删除）

### Fixed

- 客户端重构为纯 DSH 插件（React 组件 + __ModuleLoader__），消除 UI 风格不一致、白屏、手动填字段问题
- 在线状态显示修复（设备心跳注册机制）
- 成员名显示修复（去掉 React span 包裹导致的 [object Object]）

### ⚠️ IMPORTANT — 安装前必读

deepDDW 实现了独立的记忆体与知识库隔离机制。安装前请：① 备份现有记忆体与知识库；② 卸载/停用其他记忆或知识库插件；③ 避免同时运行导致数据冲突。

### Planned for v0.6.0

- 英文/中文多语言菜单支持（跟随 DSH locale 系统）
- 设置面板自定义图标（当前为默认齿轮图标）

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
