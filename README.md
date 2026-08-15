# deepDDW 0.1

deepDDW 0.1 是由 **DDW AI Hub 6.0**（商业仓，Gitea `chenye/ddw-ai-hub-workspace` @ `0f2343e`）
裁剪而来的**开源一体包**。两库自 2026-08-16 起**彻底分家、永无交集**：本仓库只含白名单组件，
商业插件、账号体系、计费授权、多租户等一律不进入本仓库。

## 组件（白名单）

| 组件 | 说明 | 许可证 |
|---|---|---|
| 底座壳 | 网关 + 插件装载框架 + Token 门禁（无账号体系） | MIT（本项目） |
| DSH 引擎 | DeepSeek Harness 官方 MIT，子进程/独立服务拉起 | MIT |
| 个人级知识库 | SQLite（FTS5/LIKE 检索），LanceDB 向量增强预留 | Public Domain / Apache-2.0 |
| 记忆 | SQLite 轻量实现（namespace/key/tags），可接 agentmemory MCP | Apache-2.0（agentmemory） |
| LiteLLM 通道 | DeepSeek（云端）+ Ollama（本地） | MIT（本项目实现） |
| SearXNG | 聚合搜索（独立服务，可选） | AGPL-3.0（服务端 HTTP 调用豁免评估通过） |
| PWA | 启动页 + 手机浏览器工作台（/ui） | MIT（本项目） |
| MCP 双协议 | streamable-http（2025-03-26）+ 经典（2024-11-05），自研 | MIT（本项目） |

> 许可证红线：仅允许 Public Domain / MIT / Apache-2.0 / BSD / PostgreSQL License；
> 禁止 SSPL / RSAL / Elastic License；GPL/AGPL 引库需评估（SearXNG 为服务端 HTTP 调用，已评估豁免）。

## 快速开始

```bash
# 本地 venv
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DDW_ACCESS_TOKEN=$(openssl rand -hex 24)   # 或写入 .env
python -m uvicorn core.main:app --host 0.0.0.0 --port 8500

# 或 Docker 一键（推荐全新服务器）
cp .env.example .env   # 填写 DDW_ACCESS_TOKEN
docker compose -f deepddw-compose.yml up -d --build
```

打开 `http://<host>:8500/` → PWA 启动页 → 填 Token → 进入工作台（会话 / 知识库 / 记忆 / 文档）。

## 安全模型（P0-1）

- 无账号体系：只有静态访问 Token（`DDW_ACCESS_TOKEN` / `config/deployment.yaml auth.access_token`）。
- 全部 MCP 端点（`/api/v1/mcp` streamable-http、`/api/v1/mcp/jsonrpc|sse|info` 经典）与网关 API
  必须携带 `Authorization: Bearer <token>` 或 `X-DDW-Token`，缺失/无效 → **401**。
- MCP `tools/list` 按白名单过滤（core / ddw-docs-portal / ddw-searxng）——商业插件工具绝不注册、绝不外露。
- 前端 iframe 内不携带明文 Token：Token 存本机会话（sessionStorage / postMessage），不进入 URL。

## MCP 接入

```jsonc
// DSH / Claude Code / 任意 MCP 客户端
{
  "mcpServers": {
    "deepddw": {
      "type": "http",
      "url": "http://<host>:8500/api/v1/mcp",
      "headers": { "Authorization": "Bearer <token>" }
    }
  }
}
```

工具：`ddw.llm.chat` / `ddw.kb.search` / `ddw.memory.put` / `ddw.memory.search` / `ddw.docs_portal.search`。

## 开发与测试

```bash
pip install -r requirements.txt
python -m pytest tests/ plugins/ -q          # 全量（含 MCP 鉴权/时序/加固）
ruff check --select=E,W,F core plugins sdk tests
```

## 目录

```
core/               底座壳（网关/插件框架/安全/LLM 网关/MCP 双协议）
plugins/            白名单插件：ddw-docs-portal、ddw-searxng
frontend/           PWA：deepddw-launcher.html / welcome.html（工作台）/ docs
sdk/                插件开发 SDK（PluginBase 等）
config/             部署配置模板（deployment.yaml 被 gitignore，不入库）
data/               运行时数据（gitignore）
```

## 分家声明

- 本仓库与 `ddw-ai-hub-workspace`（商业仓）无任何共同 remote、无互相 merge、无互相依赖。
- 本仓库不含任何商业插件代码、商业文档、密钥或客户数据。
- 本仓库不包含《deepDDW 0.1 裁剪与修复任务书》（内部策略文档）。
