# MCP Email Server 生态深度分析报告

> 调研时间：2026-07-13  
> 调研范围：marlinjai/email-mcp、codefuturist/email-mcp、ai-zerolab/mcp-email-server、1018053166/sse-email-mcp-server  
> 目的：DDW AI Hub 邮件插件 Phase 2 竞品分析

---

## 一、项目概览

MCP（Model Context Protocol）是 Anthropic 推出的 AI 助手标准协议，允许 AI 通过统一接口调用外部工具。2025-2026 年间，邮件 MCP Server 作为新兴品类快速涌现，核心目标是让 Claude Desktop、Cursor、VS Code Copilot 等 AI 助手直接读写邮件。以下对四个开源项目进行深度对比分析。

| 维度 | marlinjai/email-mcp | codefuturist/email-mcp | ai-zerolab/mcp-email-server | 1018053166/sse-email-mcp-server |
|------|---------------------|------------------------|-----------------------------|---------------------------------|
| ⭐ Stars | 16 | 70 | **280** | 4 |
| 创建时间 | 2026-02-16 | 2026-02-18 | **2025-02-24**（最早） | 2026-02-09 |
| 最后更新 | 2026-07-05 | 2026-07-13 | 2026-07-13 | 2026-06-18 |
| 语言 | TypeScript | TypeScript | **Python** | JavaScript |
| 许可证 | MIT | LGPL-3.0 | BSD-3-Clause | MIT |
| MCP 工具数 | 25 | **47** | ~15+ | 3 |
| MCP 资源 | — | 6 | 1 | — |
| MCP Prompt | — | 7 | — | — |

---

## 二、项目逐一分析

### 2.1 marlinjai/email-mcp — 多 Provider 原生 API 方案

**定位**：统一 MCP 邮件访问层，优先使用 Provider 原生 API（Gmail REST API、Microsoft Graph），回退到 IMAP。

**项目结构**：
```
src/
├── auth/              — 凭据存储（AES-256-GCM 加密）
├── providers/
│   ├── gmail/         — Gmail REST API（Google Auth Library + googleapis）
│   ├── outlook/       — Microsoft Graph（@azure/msal-node + @microsoft/microsoft-graph-client）
│   ├── icloud/        — iCloud IMAP 适配器
│   └── imap/          — 通用 IMAP/SMTP 适配器
├── tools/             — 4 类 MCP 工具（accounts/reading/sending/organizing）
├── setup/wizard.ts    — 交互式配置向导
└── models/types.ts    — 类型定义
```

**技术栈**：
- IMAP 库：**imapflow**（Node.js，支持 IDLE、连接池）
- SMTP 库：**nodemailer**（Node.js，最成熟的 SMTP 实现）
- OAuth：Google Auth Library（PKCE）、MSAL Node（PKCE）
- MCP SDK：@modelcontextprotocol/sdk ^1.26.0
- 构建：esbuild + TypeScript
- 测试：vitest

**IMAP/SMTP 实现方式**：
- IMAP：通过 imapflow 库直接连接，支持 SSL/TLS 993 端口
- SMTP：通过 nodemailer 库发送，支持 SSL 465 和 STARTTLS 587
- Gmail 和 Outlook 走原生 REST API，iCloud 和通用 IMAP 走 IMAP 协议
- 跨账户邮件转移（email_transfer）通过原始 MIME 传输实现

**支持的邮箱类型**：
- Gmail（REST API，OAuth2 PKCE）
- Outlook/Microsoft 365（Graph API，OAuth2 PKCE）
- iCloud（IMAP + App-Specific Password）
- 通用 IMAP/SMTP（任意邮箱）

**亮点**：
- 25 个 MCP 工具，覆盖完整邮件生命周期
- AES-256-GCM 加密凭据存储，机器密钥派生
- 轻量搜索模式：默认 compact results（~20KB vs ~1.4MB）
- 批量操作：支持删除/移动/标记最多 1000 封邮件
- 安装极简：`npx @marlinjai/email-mcp` 即用

**局限**：
- 不支持 QQ/163 等中国邮箱（需自行配置 generic IMAP）
- 无 Docker 支持
- 项目较新（2026-02），生态尚在成长期

---

### 2.2 codefuturist/email-mcp — 功能最全面的全生命周期方案

**定位**：功能最完整的 MCP 邮件客户端，覆盖读取、撰写、管理、调度、分析的全生命周期。是四个项目中工具数量最多（47 个工具 + 7 个 Prompt + 6 个 Resource）的方案。

**项目结构**：
```
src/
├── cli/               — CLI 命令（account/config/install/scheduler）
├── config/            — XDG 配置（TOML 格式）+ Zod 校验
├── connections/manager.ts — 懒加载持久 IMAP/SMTP 连接管理器
├── services/
│   ├── imap.service.ts     — IMAP 操作封装
│   ├── smtp.service.ts     — SMTP 操作封装
│   ├── label-strategy.ts   — Provider 感知的标签策略
│   ├── template.service.ts — 邮件模板引擎
│   ├── oauth.service.ts    — OAuth2 令牌管理（实验性）
│   ├── calendar.service.ts — ICS/iCalendar 解析
│   ├── scheduler.service.ts — 邮件调度队列
│   ├── watcher.service.ts  — IMAP IDLE 实时监听
│   ├── hooks.service.ts    — AI 分诊（MCP sampling + 静态规则）
│   ├── notifier.service.ts — 多渠道通知（桌面/声音/Webhook）
│   └── presets.ts          — 内置分诊预设
├── tools/             — 42 个 MCP 工具定义
├── prompts/           — 7 个 MCP Prompt
├── resources/         — 6 个 MCP Resource
└── safety/            — 审计日志 + 速率限制器
```

**技术栈**：
- IMAP 库：**imapflow** ^1.2.9
- SMTP 库：**nodemailer** ^8.0.1
- 配置：smol-toml（TOML 解析）
- 校验：zod ^4.3.6
- CLI：@clack/prompts（交互式向导）
- 日历：node-ical（ICS 解析）
- MCP SDK：@modelcontextprotocol/sdk ^1.26.0
- 测试：vitest + testcontainers（集成测试用 Docker 容器）

**IMAP/SMTP 实现方式**：
- IMAP：imapflow 库，支持 IDLE 实时监听、自动重连
- SMTP：nodemailer 库，支持连接池
- OAuth2（实验性）：支持 Google 和 Microsoft
- 配置文件：XDG 标准路径 `~/.config/email-mcp/config.toml`
- 连接管理器支持多账户并发、懒加载、超时控制

**支持的邮箱类型（自动检测）**：
| Provider | 域名 |
|----------|------|
| Gmail | gmail.com |
| Outlook/Hotmail | outlook.com, hotmail.com, live.com |
| Yahoo Mail | yahoo.com, ymail.com |
| iCloud | icloud.com, me.com, mac.com |
| Fastmail | fastmail.com |
| ProtonMail Bridge | proton.me, protonmail.com |
| Zoho Mail | zoho.com |
| GMX | gmx.com, gmx.de, gmx.net |
| 通用 IMAP | 任意 |

**47 个 MCP 工具分类**：
- **Read（14个）**：list_accounts, list_mailboxes, list_emails, get_email, get_emails, search_emails, download_attachment, find_email_folder, extract_contacts, get_thread, list_templates, get_email_stats, check_health, get_email_status
- **Write（9个）**：send_email, reply_email, forward_email, save_draft, send_draft, apply_template, schedule_email, list_scheduled, cancel_scheduled
- **Manage（7个）**：move_email, delete_email, mark_email, bulk_action, create_mailbox, rename_mailbox, delete_mailbox
- **Labels（5个）**：list_labels, add_label, remove_label, create_label, delete_label
- **Watcher & Alerts（6个）**：IMAP IDLE 状态、AI 分诊预设、通知配置
- **Calendar & Reminders（6个）**：ICS 解析、日历集成、提醒创建

**亮点**：
- 功能最全面：47 工具 + 7 Prompt + 6 Resource，远超同类
- IMAP IDLE 实时监听 + AI 分诊（通过 MCP sampling 调用 LLM 分类）
- 邮件调度系统（定时发送 + launchd/crontab 桌面级调度器）
- Provider 感知的标签策略（Gmail X-GM-LABELS / ProtonMail Folders / IMAP Keywords）
- 完整 Docker 支持（ghcr.io 发布）
- 多 MCP 客户端适配器（Claude Desktop / VS Code / Cursor / Windsurf / Zed / Mistral Vibe）
- 速率限制器 + 审计日志

**局限**：
- LGPL-3.0 许可证（对闭源项目不友好）
- OAuth2 支持仍为实验性
- 不支持 QQ/163 等中国邮箱的自动检测（需手动配置）
- 无 POP3 支持

---

### 2.3 ai-zerolab/mcp-email-server — 最高人气的 Python 方案

**定位**：基于 Python 的 MCP 邮件服务器，是社区中最受欢迎（280 Stars）的方案，也是最早（2025-02）创建的项目。

**项目结构**：
```
mcp_email_server/
├── app.py             — FastMCP 服务器入口 + 工具注册
├── cli.py             — Typer CLI
├── config.py          — Pydantic Settings + TOML 配置
├── keyring_store.py   — OS Keyring 集成
├── ui.py              — Gradio Web UI 配置界面
├── emails/
│   ├── classic.py     — IMAP/SMTP 经典处理器
│   ├── dispatcher.py  — 按账户类型分发到对应处理器
│   ├── models.py      — Pydantic 数据模型
│   └── provider/      — Provider 特定实现
└── tools/
    └── installer.py   — MCP 客户端自动注册器
```

**技术栈**：
- IMAP 库：**aioimaplib** ≥2.0.1（Python 异步 IMAP）
- SMTP 库：**aiosmtplib** ≥4.0.0（Python 异步 SMTP）
- MCP SDK：mcp[cli] ≥1.23.0,<2（官方 Python SDK）
- 配置：Pydantic Settings + TOML
- 凭据：keyring 库（macOS Keychain / Linux Secret Service）
- UI：Gradio ≥6.0.1（Web 配置界面）
- 构建：hatchling
- Python 版本：≥3.10

**IMAP/SMTP 实现方式**：
- IMAP：aioimaplib 异步实现，支持 STARTTLS 和自签名证书
- SMTP：aiosmtplib 异步实现
- 配置层通过 Pydantic Settings 管理，支持 TOML 文件和环境变量双通道
- 凭据存储三级策略：auto（优先 OS Keyring）/ keyring（强制）/ plaintext（纯文本）
- 支持 IMAP-only 模式（无 SMTP，只读）
- HTTP 传输安全：DNS Rebinding 防护、Host/Origin 校验

**支持的邮箱类型**：
- 通过 IMAP/SMTP 通用协议支持所有邮箱
- 无 Provider 自动检测机制，需手动配置 IMAP/SMTP 服务器参数
- 官方文档提到了 ProtonMail Bridge 兼容性

**工具列表**（从代码推断）：
- list_available_accounts — 列出配置的账户
- add_email_account — 添加账户
- list_emails_metadata — 列出邮件元数据（分页、过滤）
- get_emails_content — 获取邮件内容
- send_email — 发送邮件
- save_to_mailbox — 通过 IMAP APPEND 保存到文件夹
- delete_emails — 删除邮件
- move_emails — 移动邮件
- archive_emails — 归档邮件
- mark_emails_as_read — 标记已读
- download_attachment — 下载附件
- list_mailboxes — 列出文件夹
- list_allowed_recipients — 列出允许的收件人
- list_allowed_senders — 列出允许的发件人

**亮点**：
- Python 生态，对 DDW（Python 项目）技术栈最友好
- Gradio Web UI 配置界面，用户体验好
- OS Keyring 深度集成，安全等级高
- 凭据迁移工具（keyring ↔ plaintext）
- 多种传输模式（stdio / SSE / streamable-http）
- Docker 支持（ghcr.io 发布）
- 详细的环境变量配置表，CI/CD 友好
- 收件人/发件人白名单，适合企业场景
- BSD-3-Clause 许可证（宽松）

**局限**：
- 无 OAuth2 支持（仅密码认证）
- 无中国邮箱（QQ/163）自动检测
- 工具数量较少（~15 个），功能不如 codefuturist 全面
- 异步 IMAP 库（aioimaplib）相比 imapflow 成熟度稍逊

---

### 2.4 1018053166/sse-email-mcp-server — 中国邮箱最佳兼容方案

**定位**：面向中国用户的 MCP 邮件服务器，是唯一一个原生支持 QQ、163、126、Sina 等中国邮箱的服务。

**项目结构**：
```
src/
├── server.js          — MCP 服务器入口
├── mcp-stdio.js       — stdio 传输层
├── config/
│   └── config-loader.js — 配置加载器
├── providers/
│   ├── index.js       — Provider 工厂
│   └── providers.json — 预定义 Provider 配置
├── tools/
│   ├── send-email.js    — SMTP 发送
│   ├── receive-imap.js  — IMAP 接收
│   ├── receive-pop3.js  — POP3 接收
│   └── archive-email.js — 邮件归档
└── utils/
    └── email-validator.js — 邮箱校验
```

**技术栈**：
- IMAP 库：**imap** ^0.8.17（Node.js 同步 IMAP 库）
- SMTP 库：**nodemailer** ^8.0.0
- POP3：通过 imap 库的 POP3 支持
- 配置：dotenv + fs-extra
- Node.js ≥14.0.0（最低兼容性要求）

**IMAP/SMTP 实现方式**：
- IMAP：imap 库同步实现（非 imapflow）
- SMTP：nodemailer 库
- POP3：imap 库的 POP3 功能
- 通过 providers.json 预定义各邮箱服务商的服务器参数

**支持的邮箱类型（原生预配置）**：
| 邮箱 | SMTP | IMAP | POP3 |
|------|------|------|------|
| Gmail | smtp.gmail.com:587 | imap.gmail.com:993 | pop.gmail.com:995 |
| Outlook | smtp.office365.com:587 | outlook.office365.com:993 | outlook.office365.com:995 |
| **QQ 邮箱** | smtp.qq.com:587 | imap.qq.com:993 | pop.qq.com:995 |
| **163 邮箱** | smtp.163.com:25 | imap.163.com:993 | pop.163.com:995 |
| **126 邮箱** | — | — | — |
| **Sina 邮箱** | — | — | — |
| 自定义 | — | — | — |

**工具列表**（仅 3 个）：
1. `send_email_smtp` — 发送邮件（支持附件、HTML/纯文本、CC/BCC）
2. `receive_email_imap` — IMAP 接收（支持过滤未读、分页）
3. `receive_email_pop3` — POP3 接收

**亮点**：
- **中国邮箱兼容性最好**：QQ、163、126、Sina 原生预配置
- 三种协议支持：SMTP + IMAP + POP3（唯一支持 POP3 的项目）
- 动态认证：支持在每次工具调用时传递 auth 参数，无需存储密码
- 配置优先级清晰：auth 参数 > 环境变量 > 配置文件 > 预定义配置
- 中文文档完善，使用说明详尽
- 附带 QQ 邮箱授权码获取教程
- npm 包发布，npx 直接运行

**局限**：
- 工具数量最少（仅 3 个），功能极为有限
- 使用较老的 imap 库（非 imapflow），不支持 IDLE
- 无 OAuth2 支持
- 无批量操作
- 无搜索功能
- 无文件夹管理
- 代码质量较低（项目结构简单）
- 4 个 Stars，社区认可度低

---

## 三、横向对比分析

### 3.1 IMAP/SMTP 实现方式对比

| 项目 | IMAP 库 | SMTP 库 | 异步支持 | IDLE | 连接池 |
|------|---------|---------|----------|------|--------|
| marlinjai | imapflow | nodemailer | ✅ | ✅ | ✅ |
| codefuturist | imapflow | nodemailer | ✅ | ✅ | ✅ |
| ai-zerolab | aioimaplib | aiosmtplib | ✅ 原生异步 | ❌ | ❌ |
| sse-email-mcp | imap | nodemailer | ❌ | ❌ | ❌ |

**关键发现**：imapflow + nodemailer 是 Node.js 邮件 MCP 的事实标准组合。Python 方案则使用 aioimaplib + aiosmtplib。如果 DDW 选择 Python 技术栈，ai-zerolab 的实现方式最值得参考。

### 3.2 中国邮箱兼容性对比

| 项目 | QQ | 163 | 126 | Sina | 自动检测 |
|------|-----|------|------|------|----------|
| marlinjai | 需手动配置 | 需手动配置 | 需手动配置 | 需手动配置 | ❌ |
| codefuturist | 需手动配置 | 需手动配置 | 需手动配置 | 需手动配置 | ❌ |
| ai-zerolab | 需手动配置 | 需手动配置 | 需手动配置 | 需手动配置 | ❌ |
| sse-email-mcp | ✅ 原生 | ✅ 原生 | ✅ 原生 | ✅ 原生 | ✅ |

**关键发现**：只有 sse-email-mcp-server 原生支持中国邮箱。其他三个项目都依赖通用 IMAP/SMTP 配置，理论上可以兼容 QQ/163，但需要用户手动填写服务器参数。**DDW 插件应参考 sse-email-mcp-server 的 providers.json 设计**，将中国邮箱的 IMAP/SMTP/POP3 服务器参数预配置好，降低用户配置门槛。

### 3.3 MCP 工具定义格式对比

所有项目都使用 `@modelcontextprotocol/sdk`（Node.js）或 `mcp[cli]`（Python）官方 SDK。

**工具注册模式**：

```typescript
// Node.js（marlinjai/codefuturist）
server.tool("email_send", { to, subject, body }, handler)

// Python（ai-zerolab）
@mcp.tool(description="Send an email")
async def send_email(to: str, subject: str, body: str) -> str: ...

// JavaScript（sse-email-mcp）
server.setRequestHandler(ListToolsRequestSchema, handler)
```

**关键发现**：Python 方案（FastMCP）的工具定义最简洁，通过装饰器 + Pydantic 参数自动校验，代码量最少。DDW 作为 Python 项目，建议采用 FastMCP 模式。

### 3.4 安全机制对比

| 特性 | marlinjai | codefuturist | ai-zerolab | sse-email-mcp |
|------|-----------|--------------|------------|---------------|
| 凭据加密 | AES-256-GCM | 未明确 | OS Keyring | 环境变量 |
| TLS/STARTTLS | ✅ | ✅ | ✅ | ✅ |
| 速率限制 | ❌ | ✅ | ❌ | ❌ |
| 审计日志 | ❌ | ✅ | ❌ | ❌ |
| 收件人白名单 | ❌ | ❌ | ✅ | ❌ |
| 发件人过滤 | ❌ | ❌ | ✅ | ❌ |
| 动态认证 | ❌ | ❌ | ❌ | ✅ |

---

## 四、对 DDW AI Hub 邮件插件的启示

### 4.1 技术选型建议

1. **IMAP 库**：Python 生态下，**aiosmtplib + imaplib2**（或 aioimaplib）是主流选择。如果需要 IDLE 支持，优先考虑 imaplib2。
2. **SMTP 库**：**aiosmtplib** 是 Python 异步 SMTP 的标准选择，已被 ai-zerolab 验证。
3. **MCP SDK**：使用官方 `mcp[cli]` Python SDK，FastMCP 模式注册工具。
4. **配置管理**：参考 ai-zerolab 的 Pydantic Settings + TOML 模式。

### 4.2 中国邮箱兼容策略

参考 sse-email-mcp-server 的 **providers.json 预配置模式**，DDW 插件应内置以下中国邮箱的服务器参数：

```json
{
  "qq": { "smtp": "smtp.qq.com:587", "imap": "imap.qq.com:993", "pop3": "pop.qq.com:995" },
  "163": { "smtp": "smtp.163.com:25", "imap": "imap.163.com:993", "pop3": "pop.163.com:995" },
  "126": { "smtp": "smtp.126.com:25", "imap": "imap.126.com:993", "pop3": "pop.126.com:995" },
  "sina": { "smtp": "smtp.sina.com.cn:25", "imap": "imap.sina.com.cn:993", "pop3": "pop.sina.com.cn:995" }
}
```

同时提供用户友好的配置向导，引导用户获取 QQ 邮箱授权码等关键信息。

### 4.3 MCP 工具设计建议

基于竞品分析，DDW 邮件插件应至少实现以下核心工具集：

**必备工具（MVP）**：
- `list_emails` — 列出邮件（支持分页、过滤）
- `get_email` — 获取邮件详情
- `send_email` — 发送邮件
- `reply_email` — 回复邮件
- `search_emails` — 搜索邮件

**推荐工具（Phase 2）**：
- `delete_email` / `move_email` — 邮件管理
- `mark_email` — 标记已读/未读/星标
- `download_attachment` — 附件下载
- `list_mailboxes` — 文件夹列表

**高级工具（Phase 3）**：
- `schedule_email` — 定时发送（参考 codefuturist）
- `watch_inbox` — IMAP IDLE 实时监听
- `batch_action` — 批量操作

### 4.4 安全设计

1. 凭据存储：优先使用 OS Keyring（参考 ai-zerolab），回退到加密文件
2. 支持动态认证（参考 sse-email-mcp）：每次调用可传入 auth 参数
3. 收件人白名单（参考 ai-zerolab）：防止 AI 误发邮件到外部地址
4. 审计日志（参考 codefuturist）：记录所有邮件操作

### 4.5 架构建议

建议采用 **分层架构**（参考 codefuturist）：
```
MCP 工具层 → 业务逻辑层 → 邮件协议层（IMAP/SMTP/POP3）
                ↓
           配置管理（TOML + Keyring）
                ↓
           Provider 适配（QQ/163/Gmail/Outlook...）
```

这样可以实现：
- 协议层与业务逻辑解耦，便于测试
- Provider 适配层可扩展，新增邮箱只需添加 JSON 配置
- MCP 工具层保持薄，只负责参数转换和调用分发

---

## 五、总结

| 维度 | 最佳参考项目 | 原因 |
|------|-------------|------|
| Python 实现 | ai-zerolab/mcp-email-server | 唯一 Python 方案，技术栈最匹配 |
| 中国邮箱支持 | 1018053166/sse-email-mcp-server | 唯一原生支持 QQ/163/126/Sina |
| 功能完整度 | codefuturist/email-mcp | 47 工具 + IDLE + 调度 + 分诊 |
| 架构设计 | codefuturist/email-mcp | 分层清晰，Provider 感知 |
| 安全机制 | ai-zerolab + codefuturist | Keyring + 白名单 + 审计 |
| 简洁安装 | marlinjai/email-mcp | npx 一行启动 |

**综合建议**：DDW 邮件插件应以 **ai-zerolab 的 Python 技术栈**为骨架，融合 **sse-email-mcp-server 的中国邮箱预配置**和 **codefuturist 的分层架构与工具设计**，构建一个对中文用户友好、功能实用、安全可靠的 MCP 邮件服务。
