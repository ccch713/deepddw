# deepDDW — 让 DeepSeek Harness 具备记忆与知识库，局域网内任意设备可用

> **不只是记忆——是部署在局域网内的团队级 AI 工作台。**
>
> **为 DeepSeek Harness（DSH）补齐记忆体、知识库与内网部署能力，基于我们成熟的企业级 DDW AI HUB 底座平台构建。**
>
> - ✅ 突破 DSH 官方「仅本机使用」限制 — **局域网内任意智能设备可访问**
> - ✅ 记忆体 + 知识库 + 文档检索 — **以 DSH 官方标准 MCP 接口接入，不改 DSH 源码**
> - ✅ 整体封装、简便部署、低运维成本 — **20 人以下小型商业组织开箱即用**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 🌐 **English** · 简体中文
> 这是中文说明。英文版见 [`README.md`](README.md)。

> 💡 **deepDDW 与"纯记忆插件"的区别**：很多 DSH 扩展只提供记忆。deepDDW 是**完整的工作台**——记忆 + 知识库 + 文档检索 + **局域网多设备访问**，封装自企业级 AI 底座平台。部署一次，整个团队用自己的设备使用 DSH。

---

## 我们是谁：不只是开源工具，是商用解决方案

deepDDW 背后是 **DDW AI HUB** —— 一套经过企业级验证的 AI 底座平台。我们将成熟的底座能力封装进 DSH 生态，解决了许多开源项目尚未覆盖的三个关键场景：

| 官方 DSH 的限制 | deepDDW 的解法 |
|----------------|----------------|
| 🔒 **仅本机可用** | ✅ **局域网内任意设备访问**：服务器部署后，电脑、笔记本、手机、平板，同一个网络内的智能设备全部可用 |
| 🧠 **无记忆体** | ✅ 长期记忆写入/检索，对话经验可沉淀 |
| 📚 **无知识库** | ✅ 知识库检索/入库，行业文档、SOP、研究笔记随时调用 |

**一句话**：把"个人玩具"变成"小组织能用的工具"——**整体封装、简便部署、降低运维成本，让小型商业组织部署即可使用**，基本可以支撑 20 人以下企业的日常 AI 工作流。

---

## 它怎么工作？（技术线路）

```
📱 手机 / 💻 电脑 / 📱 平板 / 🖥️ 笔记本 —— 局域网内任意设备
   │                    （浏览器访问，无需安装 App）
   ▼
deepDDW 网关（局域网内一台服务器）
   ├─ /dsh/*   反代 → DSH 引擎（官方原版界面，模型配置/对话全原版）
   ├─ /api/*   反代 → DSH 的 RPC/API
   └─ /api/v1/*  deepDDW 能力：知识库 / 记忆体 / 文档 / LLM 配置
        │
        │  DSH 官方 MCP 客户端（streamable-http）
        ▼
deepDDW MCP 工具（模型自动调用）
   ├─ mcp__deepddw__ddw_kb_search        知识库检索
   ├─ mcp__deepddw__ddw_memory_put       写入记忆
   ├─ mcp__deepddw__ddw_memory_search    检索记忆
   └─ mcp__deepddw__ddw_docs_portal_search  文档检索
```

**接入方式 = DSH 标准 MCP**：DSH 原生支持 MCP 客户端，deepDDW 暴露标准 `streamable-http` 端点——**零侵入、不改 DSH 一行源码**，界面、设置、模型配置全部保持官方原版。

---

## 为什么你在局域网内能用？

DSH 官方出于安全考虑只监听本机（`localhost`），手机/平板根本连不上。deepDDW 通过**网关反代**解决了这个矛盾：

- **DSH 保持安全的本机绑定**（官方安全设计不被破坏）
- **deepDDW 网关统一对外**，局域网内任意设备访问 `http://<服务器IP>:8600/` 即进入 DSH 原版工作台
- 数据全部存储在你自己的服务器上，**不出内网**

**部署一台，全家/全团队可用**——这是官方 DSH 给不了的能力。

---

## 快速开始

```bash
# 1. 在服务器上安装 DSH（官方）
npm i -g @deepseek-ai/dsh

# 2. 安装 deepDDW（整体封装，一条命令）
git clone https://github.com/ccch713/deepddw.git
cd deepddw && ./install.sh --with-dsh

# 3. 启动
./install.sh --port 8600

# 4. 局域网内任意设备打开：
#    http://<服务器IP>:8600/   → DSH 原版工作台
#    手机/平板可"添加到主屏幕"获得 App 体验

# 5. 在 DSH「设置 → 模型」填 API Key
# 6. 对话里让模型"搜索知识库"或"记住 xxx" → 自动调用 mcp__deepddw__* 工具
```

**部署门槛**：一台普通电脑/服务器（最低 8GB 内存，**推荐 16GB 及以上**），Python 3.11+，无 GPU 要求（LLM 走云端 API 或本机 Ollama）。

---

## 局域网多设备联机（0.2.0）

deepDDW 面向**局域网内最多 20 台设备共享一个网关**的场景：

- **设备身份**：每台浏览器在 localStorage 持久化 `device_id`，启动页可设置设备名称；
  重连后身份不变（刷新/重启仍是同一台设备）。
- **在线状态**：设备向网关注册/心跳；`/api/v1/status`（Token 保护）返回谁在线、
  活跃 WebSocket 数、请求计数、数据库大小与版本；启动页为管理员渲染实时状态卡片。
- **网关限流**：滑动窗口，按 Token + 按 IP 双维度（默认 60 req/min/token，
  全网关总容量耗尽 → 503 过载保护）；可通过 `config/deployment.yaml` 的
  `security.rate_limit.*` 或 `DDW_RATE_LIMIT_*` 环境变量覆盖。
- **SQLite 并发加固**：所有连接统一 WAL + `busy_timeout=5000` + `synchronous=NORMAL`，
  跨表写事务走进程级写锁（已用 20 并发写验证，无 `database is locked`）。

```
POST /api/v1/device/register    # 注册/改名本设备（幂等）
POST /api/v1/device/heartbeat   # 心跳保活
GET  /api/v1/status             # 状态面板（需 Token）
```

---

## 安全与隐私

| 能力 | 说明 |
|------|------|
| 🔐 数据全本地 | 知识库/记忆存自己的服务器，不出内网 |
| 🏠 局域网免密 | 内网访问开箱即用（默认免密模式）|
| 🌐 外网访问 | 可配 Token 门禁（支持短码），未授权一律 401 |
| 🛡️ DSH 安全绑定 | DSH 只监听本机，网关统一对外，不破坏官方安全设计 |

---

## 技术栈与许可

| 组件 | 说明 | 许可 |
|------|------|------|
| DSH 引擎 | DeepSeek Harness 官方原版（不改源码） | MIT |
| deepDDW 网关 | FastAPI + SQLite + MCP 双协议 | MIT |
| 记忆/知识库 | SQLite 存储（可接 agentmemory / 向量） | MIT |
| 搜索 | 可选 SearXNG | AGPL-3.0（服务端调用豁免）|

**deepDDW 本体：MIT License** — 自由使用、修改、商用，保留版权声明即可。

---

## 生态与反馈

- **官方插件扩展**：deepDDW 保留 DSH 原生插件机制。您可通过 DSH 官方命令从 **npm 官方仓库**安装官方插件——这也是我们推荐的唯一渠道，以最大程度避免供应链投毒：
  ```bash
  dsh plugin --profile web add <npm包名>   # 仅官方 npm 仓库
  ```
  第三方插件的安全责任由用户自行查验；deepDDW 仅保障记忆体与知识库的代码完整与安全，不窃取/不利用/不贩卖用户数据。详见 [`SECURITY.md`](SECURITY.md)。
- **知识蒸馏**：我们建议您使用适合自己的**知识蒸馏 skill / 工作流**来沉淀知识——蒸馏方法论由您选择，deepDDW 提供"蒸馏产物 → 可检索知识库 → 模型可用"的完整管道；更多插件与工具正在扩展中
- **记忆/知识移植**：知识库为标准 SQLite 结构，记忆按 namespace/key/value 组织——可从其他 Agent 或工具导出移植
- **反馈**：非常欢迎您留下宝贵的使用反馈，我们将在后续版本中提供更强大的开源工具

---

## Roadmap

只列出已交付或真实在计划内的事项。

**已交付：**
- [x] **局域网多设备联机（0.2.0）** — 设备身份/在线注册表、状态面板、网关限流、SQLite WAL 并发（最多 20 台设备）
- [x] **Docker 一键部署** — `docker compose -f deepddw-compose.yml up -d --build`（已在真实 macOS arm64 主机验证：core + SearXNG 容器启动、health/MCP/chat 端到端全绿）
- [x] **会话 → 文档沉淀** — 对话经 `ddw.docs.save` / `ddw.session.docs` MCP 工具 + REST API 保存到知识库，按会话可检索可追溯
- [x] **知识库向量检索增强** — 混合检索（SQLite FTS5/LIKE + LanceDB，RRF 融合；可选，无 LanceDB 时自动降级纯关键词）

**计划中：**
- [ ] **反思与沉淀 LLM 化** — 基于最近日志自动生成每日反思；对话自动沉淀进每日记忆（基座已交付，LLM 打磨中）
- [ ] **记忆检索质量** — 关键词扩写缓存与跨层排序优化
- [ ] **Windows 打包** — 评估见 `docs/windows-packaging.md`（PyInstaller one-dir + CI 自动出包；执行阶段，待用户确认）

---

*deepDDW — 企业级底座能力，开源给每个人。*
