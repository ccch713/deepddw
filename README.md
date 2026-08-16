# deepDDW — Memory & Knowledge Base for DeepSeek Harness, Reachable from Any Device on Your LAN

> **Not just memory — a team-ready AI workstation on your LAN.**
>
> **Extends DeepSeek Harness (DSH) with memory, a knowledge base, and LAN deployment — built on our production-grade DDW AI HUB platform.**
>
> - ✅ Breaks DSH's "local-only" limit — **usable from any device on your LAN**
> - ✅ Memory + Knowledge Base + Document Search — **via DSH's official standard MCP interface; DSH source untouched**
> - ✅ Packaged, easy to deploy, low ops cost — **ready for small businesses up to ~20 people**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **English** · [简体中文](README.zh-CN.md)

> 💡 **What makes deepDDW different from memory-only plugins**: many DSH extensions give you memory *alone*. deepDDW is a **complete workstation** — memory + knowledge base + document search + **LAN-wide multi-device access**, packaged from a production-grade AI platform. Deploy once, your whole team uses DSH from their own devices.

---

## Who We Are: Not Just an Open-Source Tool — a Commercial-Grade Solution

deepDDW is built on **DDW AI HUB**, a production-grade AI platform validated in enterprise deployments. We packaged that mature platform capability into the DSH ecosystem, addressing three key gaps that many open-source projects have not yet covered:

| Official DSH limitation | deepDDW solution |
|------------------------|------------------|
| 🔒 **Local-only access** | ✅ **LAN-wide access**: deploy once on a server; desktops, laptops, phones and tablets on the same network all connect |
| 🧠 **No memory** | ✅ Long-term memory write/search — conversation experience can be accumulated |
| 📚 **No knowledge base** | ✅ Knowledge base search/ingest — industry docs, SOPs, research notes, callable anytime |

**In one sentence**: turn a "personal toy" into a tool a small team can actually use — **fully packaged, easy to deploy, low maintenance, ready for small businesses** (up to ~20 people) for their daily AI workflow.

---

## How It Works (Technical Path)

```
📱 Phone / 💻 Desktop / 📱 Tablet / 🖥️ Laptop — any device on the LAN
   │                  (browser access, no App install)
   ▼
deepDDW Gateway (one server on the LAN)
   ├─ /dsh/*   proxy → DSH engine (official UI, model config & chat untouched)
   ├─ /api/*   proxy → DSH RPC/API
   └─ /api/v1/*  deepDDW capabilities: Knowledge Base / Memory / Docs / LLM config
        │
        │  DSH official MCP client (streamable-http)
        ▼
deepDDW MCP tools (auto-invoked by the model)
   ├─ mcp__deepddw__ddw_kb_search          knowledge base search
   ├─ mcp__deepddw__ddw_memory_put         write memory
   ├─ mcp__deepddw__ddw_memory_search      search memory
   └─ mcp__deepddw__ddw_docs_portal_search document search
```

**Integration = DSH standard MCP**: DSH natively supports MCP clients; deepDDW exposes a standard `streamable-http` endpoint — **zero intrusion, zero changes to DSH source**. The UI, settings and model configuration all remain official.

---

## Why Does It Work on Your LAN?

The official DSH listens on `localhost` only (for security), so phones/tablets cannot connect. deepDDW solves this with **gateway proxying**:

- **DSH stays bound to localhost** (official security design preserved)
- **deepDDW gateway listens on the LAN**, any device opens `http://<server-ip>:8600/` to reach the original DSH workbench
- All data stays on **your** server — never leaves the LAN

**Deploy once, the whole family/team can use it** — a capability the official DSH does not provide.

---

## Quick Start

```bash
# 1. Install DSH (official) on the server
npm i -g @deepseek-ai/dsh

# 2. Install deepDDW (packaged, one command)
git clone https://github.com/ccch713/deepddw.git
cd deepddw && ./install.sh --with-dsh

# 3. Start
./install.sh --port 8600

# 4. Open from any device on the LAN:
#    http://<server-ip>:8600/   → original DSH workbench
#    Phones/tablets: "Add to Home Screen" for an App-like experience

# 5. Add your API Key in DSH Settings → Models
# 6. In chat, ask the model to "search the knowledge base" or "remember ..."
#    → it auto-invokes the mcp__deepddw__* tools
```

**Requirements**: one ordinary computer/server (**8 GB RAM minimum, 16 GB+ recommended**), Python 3.11+, no GPU needed (LLM via cloud API or local Ollama).

### Windows (standalone exe)

A Windows build is produced automatically by the `windows-build` workflow — download `deepddw-windows.zip` from the latest **Actions → Artifacts**:

```bash
# 1. Unzip anywhere (no Python/Node needed on the target machine)
deepddw-windows/deepddw.exe

# 2. Optional: point data/config at a custom location
set DDW_DATA_DIR=%USERPROFILE%\.deepddw
set DDW_ACCESS_TOKEN=<your-token>

# 3. Start (listens on 0.0.0.0:8500) → open http://<host>:8500/health
deepddw.exe
```

Upgrades are cheap: replace the whole folder with a newer zip — your data (under `%USERPROFILE%\.deepddw`) is untouched. See [`docs/windows-packaging.md`](docs/windows-packaging.md) for the full evaluation (PyInstaller one-dir + CI auto-build) and the manual build steps.

---

## Multi-Device on LAN (0.2.0)

deepDDW is built for **up to 20 devices on your LAN** sharing one gateway:

- **Device identity** — each browser persists a `device_id` (localStorage) and
  can set a friendly name on the launcher; reconnects keep the same identity.
- **Online status** — devices register/heartbeat to the gateway; `/api/v1/status`
  (Token-protected) shows who is online, active WebSockets, request counts,
  DB size and version. The launcher renders a live status card for admins.
- **Rate limiting** — sliding-window per Token + per IP (default 60 req/min/token,
  global cap → 503 overload protection); configurable via
  `config/deployment.yaml` → `security.rate_limit.*` or `DDW_RATE_LIMIT_*` env.
- **SQLite concurrency** — WAL + `busy_timeout=5000` + `synchronous=NORMAL` on
  every connection, plus a process-wide write lock for cross-table transactions
  (20 concurrent writers verified, no `database is locked`).

```
GET  /api/v1/device/register    # register / rename this device (idempotent)
POST /api/v1/device/heartbeat   # keep-alive
GET  /api/v1/status             # status panel (token required)
```

---

## Security & Privacy

| Capability | Description |
|-----------|-------------|
| 🔐 Local-only data | Knowledge base & memory stay on your server, never leave the LAN |
| 🏠 LAN password-free | Out-of-the-box access on your LAN (password-free mode by default) |
| 🌐 External access | Optional Token gate (short-code supported); unauthorized → 401 |
| 🛡️ DSH secure binding | DSH stays on localhost; gateway exposes it — official security design preserved |

---

## Tech Stack & License

| Component | Description | License |
|-----------|-------------|---------|
| DSH engine | Official DeepSeek Harness (source untouched) | MIT |
| deepDDW gateway | FastAPI + SQLite + MCP dual-protocol | MIT |
| Memory / Knowledge base | SQLite storage (agentmemory / vectors optional) | MIT |
| Search | Optional SearXNG | AGPL-3.0 (server-side HTTP, exemption assessed) |

**deepDDW itself: MIT License** — free to use, modify, and commercially deploy; keep the copyright notice.

See [`NOTICE`](NOTICE) for full third-party attribution.

---

## Ecosystem & Feedback

- **Extend with official DSH plugins**: deepDDW keeps DSH's native plugin mechanism intact. Install official plugins straight from the npm registry via the DSH official command — the only channel we recommend, to avoid supply-chain poisoning:
  ```bash
  dsh plugin --profile web add <npm-package>   # official npm registry only
  ```
  See [`SECURITY.md`](SECURITY.md) for our third-party plugin disclaimer and what deepDDW guarantees (memory & knowledge base only; no data theft/exploitation/sale).
- **Knowledge distillation**: use whatever **distillation skill / workflow** you prefer — the methodology is yours; deepDDW provides the complete pipeline "distilled output → searchable knowledge base → model-usable". More plugins and tools are on the way.
- **Memory / knowledge migration**: knowledge base uses standard SQLite; memory is organized by namespace/key/value — import from other agents or tools.
- **Feedback**: we'd love to hear how you use it; stronger open-source tools are coming in future releases.

---

## Roadmap

Only items actually planned or already delivered are listed here.

**Delivered:**
- [x] **Multi-device on LAN (0.2.0)** — device identity/online registry, status panel, rate limiting, SQLite WAL concurrency (up to 20 devices)
- [x] **Docker one-click deployment** — `docker compose -f deepddw-compose.yml up -d --build` (verified on a real macOS arm64 host: core + SearXNG containers up, health/MCP/chat end-to-end green)
- [x] **Session → document auto-ingest** — conversations saved to the knowledge base via `ddw.docs.save` / `ddw.session.docs` MCP tools + REST API, searchable and traceable per session
- [x] **Vector search enhancement** — hybrid retrieval (SQLite FTS5/LIKE + LanceDB, RRF fusion; optional, degrades to keyword-only when LanceDB is absent)

**Planned:**
- [ ] **Reflection & consolidation powered by LLM** — daily reflection auto-generated from recent logs; conversation auto-consolidation into daily memory (base layer done, LLM polish ongoing)
- [ ] **Memory search quality** — keyword-expansion caching and cross-layer ranking improvements
- [ ] **Windows packaging** — evaluated: see `docs/windows-packaging.md` for the recommended maintainable path (evaluation stage; execution follows user decision)

---

*deepDDW — enterprise-grade capability, open-sourced for everyone.*
