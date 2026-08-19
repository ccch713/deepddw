# Changelog

All notable changes to deepDDW are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.1] - 2026-08-20

> **修复了多用户设置面板无法加载、间歇性 API 请求失败、成员在线状态不准确三大问题。**

### Fixed — 插件加载（面板无法显示）

- **客户端 Bundle 未注册** — `ddw-teams-panel` 加入 web profile 的 `dsh.profile.bundles`，浏览器半区（client.js）得以加载
- **插件依赖声明缺失** — `dsh.client.inject` 补全 5 个客户端服务依赖（runtime/connection/ui-slots/ui-settings/ui-sidebar）
- **服务白名单缺失** — client.js `exports.inject` 恢复 `['slots']`（DSH 客户端 ctx 属性访问白名单，未声明即抛 `cannot get property "slots" without inject`）
- **非法 ctx 访问** — 移除 `ctx.config` 直读（未注入属性禁止访问）
- **网关地址错误** — BASE 由 `window.location.origin`（DSH web）修正为 deepDDW 网关 `http://127.0.0.1:8500`

### Fixed — 运行稳定性（间歇性 Load failed）

- **远程访问 CORS** — 新增 `DDW_CORS_EXTRA_ORIGINS` 配置，支持 https 远程访问入口
- **keep-alive 连接复用** — 服务端 `--timeout-keep-alive 75`（默认 5 秒过短导致浏览器复用到已关闭连接）
- **面板请求容错** — 4 个 API 各自独立 catch，单端点失败不再拖垮面板；关键请求失败自动重试 3 次
- **面板刷新竞态** — refresh 保留旧数据仅置 loading，切回不闪烁空白

### Fixed — 在线状态与数据

- **成员长时间灰色** — 新增 30 秒设备心跳（deepDDW 在线判定窗口 60s，原仅页面加载注册一次）
- **device_ids 空字符串污染** — member_id 为空时不再调用 identify；清理存量脏数据

### Changed

- 插件 package.json 加 `"type": "module"`（消除服务端 ESM 警告）
- 建立 **tsdown 构建管线**（`src/client/index.ts` 权威源 → `lib/client.js`），消除手工转译漂移
- 新增 `start.sh` 启动脚本 + launchd 开机自启

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
