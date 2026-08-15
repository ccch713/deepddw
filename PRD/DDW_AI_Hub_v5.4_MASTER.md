# DDW AI Hub Platform v5.4 · 完整需求与架构文档

> **版本**：v5.4（最终合并版）
> **日期**：2026-06-27
> **文档性质**：提供给多 Agent 协作开发的唯一需求源头
> **目标**：一份文档 = 所有 Agent 都能直接上手写代码

---

## 目录

1. [项目定位](#1-项目定位)
2. [系统架构总览](#2-系统架构总览)
3. [双轨开发说明](#3-双轨开发说明)
4. [技术栈与版本锁定](#4-技术栈与版本锁定)
5. [核心代码架构](#5-核心代码架构)
6. [数据库设计（多引擎 ORM）](#6-数据库设计多引擎-orm)
7. [API 接口定义](#7-api-接口定义)
8. [LLM Gateway](#8-llm-gateway)
9. [IM 平台集成](#9-im-平台集成)
10. [插件架构与 SDK](#10-插件架构与-sdk)
11. [DataConnector 框架](#11-dataconnector-框架)
12. [v5.3 12 项补充设计](#12-v53-12-项补充设计)
13. [新功能：定价与生态](#13-新功能定价与生态)
14. [新功能：渠道商体系](#14-新功能渠道商体系)
15. [新功能：防破解体系](#15-新功能防破解体系)
16. [新功能：开发者联调](#16-新功能开发者联调)
17. [新功能：插件关系图谱+套装](#17-新功能插件关系图谱套装)
18. [新功能：插件主页双视图](#18-新功能插件主页双视图)
19. [新功能：安全防护](#19-新功能安全防护)
20. [部署方案与双模架构](#20-部署方案与双模架构)
21. [WBS 阶段划分](#21-wbs-阶段划分)
22. [附录 A：技术选型与 Pitfalls](#22-附录-a技术选型与-pitfalls)
23. [附录 B：Plugin SDK 指南](#23-附录-bplugin-sdk-指南)

---

## 1. 项目定位

**DDW AI Hub Platform（渡笃微AI底座平台）**——面向中国中小企业的 AI 应用底座平台。

核心价值：**破信息孤岛、连接现有系统、插件化可扩展**。
- 企业已有烟囱系统（ERP/MES/WMS） → DataConnector 打通
- AI 时代的新烟囱 → 底座平台统一收敛
- 钉钉/飞书/企微 → 统一 IM 入口，员工零学习成本

**部署模式**（双模，同一份代码）：
- Standalone：SQLite + Python 3.11，零 Docker 依赖，适合家庭/小企业验证
- Cloud：PostgreSQL + Redis + Caddy，适合 SME 生产环境

**定价体系**（与代码无关，Metering 框架做可开关）：
- 第 1 层：底座平台企业版一次性授权 ¥4,999-19,999
- 第 2 层：市场插件按企业人数阶梯订阅（插件作者定价）
- 第 3 层：员工公共服务 ¥1.99-4.99/月/人

---

## 2. 系统架构总览

```
LAYER 0 · 接入层（IM 适配器）
  钉钉（Stream WS，主入口）/ 飞书（预留）/ 企微（预留）/ H5 小程序

LAYER 1 · 网关与中间件
  API Versioning / Auth（JWT+PIN+SMS）/ TenantMiddleware / Audit Log / Dir Sync / Hot Reloader

LAYER 2 · 核心引擎
  Message Router / Plugin Manager / Skill Manager（三层去重+软链+级联）/ Cron Tasks / Dep Resolver

⚡ EventBus（进程内 Pub/Sub → 多 Worker 降级 Redis Pub/Sub）

LAYER 3 · LLM Gateway
  ★ MiniMax M3（默认锁死）/ DeepSeek V4 Pro（降级）/ Ollama（ds-coder-v2:16B-lite-instruct-q4_K_M，兜底）
  Routing Engine / Usage & Cost Monitor

LAYER 4 · 业务插件层
  受信任插件（进程内）：medical_records / error_management / skill_mgmt / knowledge_notes
  第三方插件（沙箱 JSON-RPC 子进程）：isolation: process

LAYER 5 · 数据抽象层
  ORM（SQLAlchemy + Alembic）/ Caching（进程内/Redis）/ File Storage（本地/OSS）
  Billing / Licensing Metering

LAYER 6 · SDK 与生态
  Plugin SDK / i18n / Test Framework / Marketplace Protocol / 一键安装脚本
```

**纯平台架构**：本架构不依赖任何特定硬件或云服务商。可部署到任意 Linux/macOS 环境。

完整架构图详见：`PRD/ddw-architecture-platform-only.html`

---

## 3. 双轨开发说明 🔴 🔵 最关键

本平台将同时由**两个独立的 LLM Agent** 同步开发，最终对比代码质量。

### 3.1 代码仓库分配

| Agent | 模型 | Gitea 仓库 | 本地路径 | 开发职责 |
|---|---|---|---|---|
| 🔴 **本地 LLM** | Ollama `deepseek-coder-v2:16b-lite-instruct-q4_K_M` | [chenye/ddw-ai-hub-local](http://localhost:3001/chenye/ddw-ai-hub-local) | `/Users/chenye/workspace/ddw-ai-hub/local-llm/` | 完整平台代码 |
| 🔵 **云 LLM** | DeepSeek V4 Pro / MiniMax M3 | [chenye/ddw-ai-hub-cloud](http://localhost:3001/chenye/ddw-ai-hub-cloud) | `/Users/chenye/workspace/ddw-ai-hub/cloud-llm/` | 完整平台代码 |

**两个 Agent 各自独立完成全部代码，不做代码共享。** 最后对比：哪一版质量更高、运行更稳、文档更完善。

### 3.2 代码标记规则

本文档中各章节标注了：

- **🔴 [LOCAL]** → 本地 LLM Agent（Ollama）写入路径：`local-llm/`
- **🔵 [CLOUD]** → 云 LLM Agent 写入路径：`cloud-llm/`
- **🟢 [SHARED]** → 两个 Agent 各自独立实现（不做复用）

所有代码必须在 Gitea 对应仓库中提交。

### 3.3 公共文件夹（两个 Agent 共享参照）

```
/Users/chenye/workspace/ddw-ai-hub/PRD/              # 本 PRD + 架构图
/Users/chenye/Documents/Obsidian Vault/03_项目/统一框架/DDW_AI_Hub_v5.4/  # Obsidian 副本
```

---

## 4. 技术栈与版本锁定

**🟢 [SHARED] — 两个 Agent 独立实现，但必须使用以下技术栈**

| 层 | 技术 | 版本 | 说明 |
|---|---|---|---|
| 运行时 | Python | ≥ 3.11, < 3.14 | 3.12 推荐 |
| Web 框架 | FastAPI | ≥ 0.110.0 | Uvicorn + Gunicorn |
| 数据库 | SQLAlchemy | ≥ 2.0.30 | Async + Alembic |
| 数据库驱动 | asyncpg / aiomysql / aiosqlite / aioodbc / cx_oracle | 最新 | EngineFactory 配置 |
| 认证 | PyJWT | ≥ 2.8.0 | RSA256 签名 |
| LLM SDK | openai | ≥ 1.30.0 | OpenAI 兼容格式 |
| 事件 | 进程内 EventBus / Redis (redis-py) | ≥ 5.0 | 单 Worker 用进程内 |
| 模板 | Jinja2 | ≥ 3.1 | 管理后台 |
| 测试 | pytest | ≥ 8.0 | + httpx AsyncClient |
| PDF | weasyprint 或 pdfkit | 最新 | POC 报告生成 |
| 加密 | cryptography | ≥ 42.0 | RSA 签名 + AES-256 |

**禁止使用**（保持对比公平）：LangChain、LlamaIndex、CrewAI 等 Agent 框架。全部手写 FastAPI + SQLAlchemy。

---

## 5. 核心代码架构

**🟢 [SHARED] — 各自在 repo 根目录按此架构创建**

```
ddw-ai-hub/                     # 两个 Agent 各自创建
├── core/                       # 核心平台（写一次，通用）
│   ├── __init__.py
│   ├── main.py                 # FastAPI app 入口 + 中间件注册
│   ├── config.py               # 配置加载（deployment.yaml）
│   ├── middleware/
│   │   └── tenant.py           # §18.1 租户隔离中间件
│   ├── auth/                   # JWT + PIN + SMS + 白名单
│   ├── router/                 # 消息路由（IM → LLM/插件）
│   ├── llm_gateway/            # 混合 LLM 路由（7 个文件）
│   │   ├── base.py             # BaseLLMProvider 抽象基类
│   │   ├── minimax.py          # MiniMax M3/M2.7 实现
│   │   ├── deepseek.py         # DeepSeek V4 Pro 实现
│   │   ├── ollama.py           # Ollama 本地实现
│   │   ├── router.py           # 路由引擎 + 降级
│   │   ├── gateway.py          # Gateway 统一入口
│   │   └── usage.py            # Token 计量 + 成本监控
│   ├── plugin_manager/         # 插件注册/发现/加载/权限/沙箱
│   │   ├── manager.py          # 插件管理器
│   │   ├── dependency_resolver.py  # §18.3 版本冲突检测
│   │   ├── sandbox.py          # §18.7 进程沙箱（JSON-RPC）
│   │   └── installer.py        # 插件安装（.ddwplugin）
│   ├── im_adapters/            # IM 适配器层
│   │   ├── base.py             # 抽象接口
│   │   ├── dingtalk/           # 钉钉 Stream Mode（Phase 1 完成）
│   │   ├── feishu/             # 飞书骨架（Phase 2）
│   │   └── wecom/              # 企微骨架（Phase 2）
│   ├── skill_manager/          # 技能去重（三层匹配）
│   ├── connectors/             # DataConnector 框架
│   ├── billing/                # Metering 框架（可开关）
│   ├── events/
│   │   ├── event_bus.py        # §18.2 进程内 EventBus
│   │   └── redis_bus.py        # 多 Worker Redis Pub/Sub
│   ├── api_versioning/
│   │   └── version_router.py   # §18.6 API 版本化
│   ├── reload/
│   │   └── hot_reload.py       # §18.5 配置热更新
│   ├── marketplace/
│   │   └── registry.py         # §18.9 插件市场协议
│   └── licensing/
│       └── license_manager.py  # §18.10 许可管理
├── plugins/                    # 业务插件（按需安装）
│   ├── medical_records/        # 病历管理
│   ├── error_management/       # 错题管理
│   ├── skill_management/       # 技能管理
│   └── _template/             # 插件模板
├── sdk/                        # Plugin SDK
│   ├── plugin_base.py          # 插件基类
│   ├── config_manager.py       # §18.8 插件级配置
│   ├── i18n.py                 # §18.11 国际化
│   └── testing/
│       └── fixtures.py         # §18.12 测试框架
├── scripts/                    # 工具脚本
│   ├── install.sh              # 一键安装（Standalone+Cloud）
│   └── init_admin.py           # 初始化管理员
├── data/                       # SQLite 数据（Standalone 模式）
├── config/                     # 配置文件
│   ├── deployment.yaml         # 双模配置
│   └── Caddyfile               # 反代配置（Cloud 模式）
├── tests/                      # 平台级测试
├── requirements.txt            # 依赖锁定
└── .env.example                # 环境变量模板
```

---

## 6. 数据库设计（多引擎 ORM）

**🟢 [SHARED] — 6 种引擎等深适配，代码已有设计参考**

详细设计见：`v5.2_PRD.md §3.3 数据库设计`（第三篇全文，11127 行中的 §3.1-§3.9）

### 6.1 EngineFactory

支持 6 种数据库引擎，实现同等深度抽象（PG / MySQL / MariaDB / SQLite / SQL Server / Oracle）

**核心接口**（文件：`core/database/factory.py`）：

```python
class EngineFactory:
    def __init__(self, config: dict): ...
    def create_engine(db_name) -> AsyncEngine: ...
    def get_session_factory(db_name) -> sessionmaker: ...
    async def init_all_databases(): ...
    async def health_check(db_name) -> dict: ...
```

### 6.2 ORM 模型基类

所有 Model 继承 `Base = declarative_base()`，加上 `TimestampMixin` 和 `TenantMixin`。

### 6.3 数据实例规划（config 驱动）

```yaml
databases:
  main:           # family_hub_core
    engine: sqlite     # Standalone: sqlite / Cloud: postgresql
    path: ./data/ddw_main.db
  medical_records:
    engine: sqlite
    path: ./data/ddw_medical.db
  error_management:
    engine: sqlite
    path: ./data/ddw_errors.db
  audit:
    engine: sqlite
    path: ./data/ddw_audit.db
```

### 6.4 全部表结构（28 张 + N 张插件表）

见 `v5.2_PRD.md §3.4-§3.8`（核心 11 张 + 病历 6 张 + 错题 4 张 + 计费 5 张 + 审计 1 张 + 配置 1 张）

---

## 7. API 接口定义

**🟢 [SHARED] — 实现同一套 API 规格**

完整 API 定义见：`v5.1_PRD.md §5.2`（第五篇全文，已补全 ~650 行）

### 7.1 通用规范

- Base URL：`/api/v1/...`
- 认证：`Authorization: Bearer <JWT>`（RSA256）
- 响应：统一 `{code, message, data, timestamp}`
- SSE：`Content-Type: text/event-stream`
- 分页：`?page=1&page_size=20&sort_by=created_at&sort_order=desc`

### 7.2 模块列表

| 模块 | 前缀 | 主要端点 | 来源 |
|---|---|---|---|
| 认证 | `/api/v1/auth/` | 短信验证码、登录、PIN、H5 免登 | v5.1 §5.2.1 |
| 用户管理 | `/api/v1/users/` | 个人信息、白名单、管理员 | v5.1 §5.2.2 |
| LLM 管理 | `/api/v1/llm/` | Provider 配置、路由规则、健康检查 | v5.1 §5.2.3 |
| 聊天 | `/api/v1/chat/` | SSE 流式、语音、图片、文件、历史 | v5.1 §5.2.4 |
| 用户间消息 | `/api/v1/messages/` | 发送、列表、已读 | v5.1 §5.2.5 |
| 技能管理 | `/api/v1/skills/` | CRUD、去重、软链接 | v5.1 §5.2.6 |
| 知识库 | `/api/v1/knowledge/` | 笔记元数据、搜索 | v5.1 §5.2.7 |
| 定时任务 | `/api/v1/cron/` | 创建、日志、触发 | v5.1 §5.2.8 |
| 病历管理（插件） | `/api/v1/plugins/medical/` | 患者/病历/附件/A1/预约 | v5.1 §5.2.9 |
| 错题管理（插件） | `/api/v1/plugins/errors/` | 错题/OCR/同类题/统计 | v5.1 §5.2.10 |
| 插件管理 | `/api/v1/admin/plugins/` | 注册/安装/卸载/启用/禁用 | v5.1 §5.2.11 |
| 连接器管理 | `/api/v1/admin/connectors/` | 配置/测试/数据预览 | v5.1 §5.2.12 |
| 系统管理 | `/api/v1/admin/system/` | 健康/配置/日志/缓存 | v5.1 §5.2.13 |
| 计费管理 | `/api/v1/admin/billing/` | 租户/订阅/用量/账单 | v5.1 §5.2.14 |
| 市场 | `/api/v1/market/` | 插件搜索/下载/安装/套装图谱 | §18.9 新增 |

---

## 8. LLM Gateway

**🟢 [SHARED] — 各自实现 Provider + 路由**

见：`v5.1_PRD.md §7`（第七篇全文，~310 行）

### 8.1 降级链

```
MiniMax M3（默认，锁死）→ DeepSeek V4 Pro（复杂分析/备用）→ Ollama 本地（兜底）
```

### 8.2 路由规则设计

见 v5.1 §7.7。核心策略：
- 日常聊天 → MiniMax M3（¥0.004/次）
- 简单查询 → Ollama 本地 16B（¥0）
- 复杂分析 → DeepSeek V4 Pro（¥0.01/次）
- 超长文档 → MiniMax 1M 上下文（¥0.02/次）
- 高频命中 Skill → 本地缓存 → Ollama（¥0）

### 8.3 MiniMax 特殊处理

见 v5.1 §7.3。MiniMax 支持多模态（图片识别/音乐/视频），接入方式为 OpenAI 兼容 SDK，但有特殊多模态矩阵需适配。

---

## 9. IM 平台集成

**Phase 1 定义**：
- 🔴 **[LOCAL]** / 🔵 **[CLOUD]** 各自实现 **钉钉 Stream Mode 主入口**（扫码对接）
- 飞书/企微适配器仅留骨架（Phase 2）

见：`v5.1_PRD.md §8`（第八篇全文，~430 行）

### 9.1 IM 适配器统一接口

```python
class BaseIMAdapter(ABC):
    async def send_message(chat_id, content) -> str
    async def send_card(chat_id, card_data) -> str
    async def handle_incoming(message) -> dict
    async def get_user_info(user_id) -> dict
```

### 9.2 Phase 1 需要实现的

- 钉钉扫码绑定 → 平台接收消息
- 消息路由 → LLM 回复 → 推送回钉钉
- 钉钉通讯录同步

---

## 10. 插件架构与 SDK

**🟢 [SHARED] — 各实现 Plugin SDK**

见：`v5.2_PRD.md §4`（第四篇全文，~400 行）

### 10.1 插件生命周期

```
安装（市场下载 .ddwplugin）→ 注册（验证 manifest）→ 加载（进程内或沙箱）→ 启用（路由注册）→ 停用 → 卸载
```

### 10.2 manifest.yaml 规范

```yaml
name: medical_records
version: 1.0.0
engine: ">=0.1.0"
dependencies:
  plugins: {}
events:
  produces: ["record.created", "record.updated"]
  consumes: ["patient.registered"]
isolation: inline          # inline | process（沙箱）
permissions:
  - "database:medical_records"
  - "api:patient:read"
```

### 10.3 .ddwplugin 包格式

加密打包规范见 v5.3 §18.9。包含：manifest.yaml + 代码 + 签名 + locales 等。

---

## 11. DataConnector 框架

**🟢 [SHARED] — 4 种连接器全部实现（SME 核心需求）**

见：`v5.1_PRD.md §9`（第九篇全文，~740 行）

### 11.1 连接器类型

| 类型 | 用途 | 安全策略 |
|---|---|---|
| REST API | 对接用友/金蝶云等标准 HTTP 接口 | 只读模式 |
| DB Direct | 直连 PG/MySQL/SQL Server | 只读模式 |
| File Import | CSV/Excel 批量导入 | 沙箱解析 |
| AI Query | 自然语言 → SQL 自动查询 | 参数化防注入 |

---

## 12. v5.3 12 项补充设计

**🟢 [SHARED] — 12 项全部实现，按优先级**

见：`v5.3_PRD.md §18`（第十八篇全文，~1200 行）

### 12.1 Phase 1 必须实现的（高优先级）

| # | 项目 | 文件 | 引用 |
|---|---|---|---|
| 1 | TenantMiddleware | `core/middleware/tenant.py` | §18.1 |
| 2 | EventBus（进程内） | `core/events/event_bus.py` | §18.2 |
| 3 | Dependency Resolver | `core/plugin_manager/dependency_resolver.py` | §18.3 |
| 4 | Hot Reloader | `core/reload/hot_reload.py` | §18.5 |
| 5 | API Versioning | `core/api_versioning/version_router.py` | §18.6 |
| 6 | Plugin Config | `sdk/config_manager.py` | §18.8 |

### 12.2 Phase 2 实现的（中优先级）

| # | 项目 | 文件 | 引用 |
|---|---|---|---|
| 7 | Scaling（多 Worker） | `core/scaling/worker_config.py` | §18.4 |
| 8 | Plugin Sandbox | `core/plugin_manager/sandbox.py` | §18.7 |
| 9 | Marketplace | `core/marketplace/registry.py` | §18.9 |
| 10 | Licensing | `core/licensing/license_manager.py` | §18.10 |

### 12.3 Phase 3（低优先级）

| # | 项目 | 文件 | 引用 |
|---|---|---|---|
| 11 | i18n | `sdk/i18n.py` | §18.11 |
| 12 | Test Framework | `sdk/testing/fixtures.py` | §18.12 |

---

## 13. 新功能：定价与生态

**🟢 [SHARED] — Metering 框架，数字不写死**

### 13.1 三层定价架构

| 层 | 比喻 | 定价模式 | 支付方 |
|---|---|---|---|
| 底座平台 | 买地 + 打地基 | 一次性授权（开源免费 / ¥4,999 / ¥19,999） | 企业方 |
| 市场插件 | 装修 + 收租 | 按企业人数阶梯订阅（插件作者定价） | 企业方 |
| 公共服务 | 水电费 | ¥1.99-4.99/月/人（低价走量） | 打工牛马 |

### 13.2 Metering 框架设计

- 底座层：`core/billing/metering.py` — 用量记录（Token / API 调用 / 插件激活数）
- 开关控制：`config/deployment.yaml` → `billing.enabled: false`（家庭部署默认关闭）
- 插件结算：插件 SDK 提供 `billing.record_usage()` 钩子
- 所有定价数字从配置文件读取，不在代码里硬编码

---

## 14. 新功能：渠道商体系

**🟢 [SHARED] — 市场管理 API + 渠道后台**

### 14.1 账号层级

```
大账号（总代/区域代理）
  ├─ 小账号 A（FDE 前端交付工程师）
  ├─ 小账号 B（销售）
  └─ 小账号 C（售后支持）
       ↓ 所有账号同时也是「开发者」身份
```

### 14.2 分润配置

```yaml
# config/commission.yaml （两个 Agent 各自实现）
commission:
  platform:
    channel_ratio: 0.60    # 底座平台 60% 给渠道
    platform_ratio: 0.40   # 平台留 40%
  plugin:
    channel_ratio: 0.05    # 插件 5% 给渠道
    platform_ratio: 0.15   # 平台抽 15%
    developer_ratio: 0.80  # 插件作者拿 80%
```

### 14.3 渠道商 API

- 注册/审核 / 小账号管理 / 客户管理 / 分润报表 / 提现

---

## 15. 新功能：防破解体系

**🟢 [SHARED] — 3 层防线全部实现**

### 15.1 原理

不用信任本地时钟，只信任 RSA 密码学签名。**降解模式代替红字警告**。

### 15.2 三层防线

| 防线 | 方法 | 代码文件 |
|---|---|---|
| ① 时间胶囊 | 市场 API 签发 RSA 签名 JSON（含 trial_start/end、设备指纹） | `core/licensing/time_capsule.py` |
| ② 设备指纹 | `sha256(MAC + disk_serial + hostname + uuid)` | `core/licensing/fingerprint.py` |
| ③ 降解模式 | 试用到期后插件不停止、不弹窗，进入"慢性降解" | 在 Plugin SDK 中 |

### 15.3 降解模式配置（manifest.yaml）

```yaml
trial:
  duration_days: 7
  expired_behavior: degraded   # stop / degraded / free_tier
  degradation:
    daily_limit: 20
    response_delay_ms: [3000, 8000]   # 随机延迟 3-8 秒
    data_quality: 0.98                 # 2% 概率插入乱码
    watermark: true                    # PDF/报告加水印
    skip_probability: 0.1              # 10% 跳过本次操作
    features:
      - "auto_backup_disabled"
      - "batch_import_disabled"
```

### 15.4 POC 报告自动生成

`core/reports/poc_generator.py` — 试用期间记录 POC 验证数据 → 导出 PDF → 含在线核验链接。降解模式下生成的报告显示"⚠️ 试用验证失败"水印。

---

## 16. 新功能：开发者联调

**🟢 [SHARED] — 复用时间胶囊签名体系**

### 16.1 流程

1. 开发者 B 在市场找到付费插件 A → 点击 "申请联调授权"
2. 平台私信通知插件作者 A
3. A 在后台审批 → 选择授权期限（14天/30天/自定义）
4. 市场 API 签发 **联调许可证**（复用 §15.2 时间胶囊签名）
5. B 的开发环境激活，插件显示 "⚡ DEV 联调模式" 水印
6. 到期前 3 天自动提醒 → A 可续签

### 16.2 技术实现

联调许可证 = 同一套 RSA 签名时间胶囊机制，只在 manifest.purpose 字段标记 `purpose: "integration"`。

---

## 17. 新功能：插件关系图谱 + 套装

**🟢 [SHARED] — manifest.yaml 新增 ecosystem 段，市场前端解析**

### 17.1 manifest 声明

```yaml
ecosystem:
  name: "口腔诊所标准方案"
  level: "industry_solution"
  plugins:
    - medical_records:
        role: "core"
    - a1_voice:
        role: "data_input"
        depends_on: ["dingtalk_adapter"]
    - appointment:
        role: "scheduling"
        depends_on: ["sms_notification"]
  bundles:
    - id: "starter"
      name: "基础入门包"
      plugins: ["medical_records", "dingtalk_adapter"]
      price_multiplier: 0.85
    - id: "complete"
      name: "全套运营包"
      plugins: ["全部"]
      price_multiplier: 0.70
```

### 17.2 市场前端

- 支持 /market/bundles/:id 套装详情页
- 关系图谱自动绘制（SVG 或 Canvas）
- 套装价格 = SUM(插件单价) × multiplier

---

## 18. 新功能：插件主页双视图

**🟢 [SHARED] — 两个 Agent 各自实现前端**

URL：`/market/plugins/{name}`（业务视图，默认）↔ `/market/plugins/{name}/dev`（开发者视图）

| 业务视图 | 开发者视图 |
|---|---|
| 截图/演示视频 / 一句话定位 / ROI 计算器 / 推荐套装 / 试用按钮 / 定价 / 部署要求 | README 渲染 / 版本历史 / API 文档 / 依赖图谱 / 源码预览 / License / 联系作者 |

---

## 19. 新功能：安全防护

**🟢 [SHARED]**

| 攻击类型 | 防御 | 实现位置 |
|---|---|---|
| AI 爬虫 | 市场 API 限流（每账号每日 50 次）+ 仅认证开发者下载 | `core/marketware/ratelimit.py` |
| 反编译 | 插件可选 pyarmor 混淆 + 运行时双重验证 | Plugin SDK |
| 供应链投毒 | 插件包 RSA 签名 + 沙箱隔离 + 权限声明 | `core/plugin_manager/signature.py` |
| 网络攻击 | Caddy HTTPS + UFW + CrowdSec + JWT + ORM 防注入 + 审计日志 | 已有基础设施 |
| 数据泄露 | AES-256 加密病历数据 + 租户隔离 + 审计追踪 | `core/security/` |

---

## 20. 部署方案与双模架构

**🟢 [SHARED]**

### 20.1 Standalone 模式（家庭/小企业验证）

```bash
git clone <repo> /opt/ddw-ai-hub
cd /opt/ddw-ai-hub
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # 编辑配置
python scripts/init_admin.py    # 初始化管理员
uvicorn core.main:app --port 8500
```

- 数据库：SQLite
- 零 Docker、零外部依赖

### 20.2 Cloud 模式（SME 生产）

```bash
docker compose up -d
# 自动启动：Caddy + FastAPI + PostgreSQL + Redis
alembic upgrade head
python scripts/init_admin.py
```

### 20.3 双模切换（deployment.yaml）

```yaml
mode: standalone   # standalone | cloud
```

---

## 21. WBS 阶段划分

**代码编写顺序（两个 Agent 各自独立遵循）：**

### Phase 1（完成核心闭环）

| 周 | 任务 | Agent 职责 |
|---|---|---|
| 1 | Core 骨架（main.py + middleware + config + auth） | 🔴 [LOCAL] + 🔵 [CLOUD] |
| 2 | EngineFactory + ORM Model（28 张表 + Alembic） | 各自实现 |
| 3 | API 端点全部（§7.2 列表）+ 通用测试 | 各自实现 |
| 4 | LLM Gateway（3 Provider + Routing + Usage） | 各自实现 |
| 5 | EventBus + Plugin Manager + Dependency Resolver | 各自实现 |
| 6 | 钉钉适配器（扫码对接）+ 基础消息路由 | 各自实现 |
| 7 | Plugin SDK + 示例插件 medical_records | 各自实现 |
| 8 | Installer 脚本（Standalone + Cloud）+ 验证 | 各自实现 |

### Phase 2（SME 功能补全）

| 周 | 任务 | 优先级 |
|---|---|---|
| 9 | DataConnector（4 种全实现）+ TenantMiddleware | SME 核心 |
| 10 | Plugin Sandbox + 插件市场 API + Licensing | SME 核心 |
| 11 | 渠道商后台 + Metering 框架 + 防破解 | SME 核心 |
| 12 | 飞书/企微适配器补全 + i18n | 体验 |

### Phase 3（生态运营）

| 周 | 任务 | 优先级 |
|---|---|---|
| 13 | 插件关系图谱 + 套装 + 双视图页面 | 市场 |
| 14 | POC 报告生成 + 降解模式 + 联调授权 | 防破解 |
| 15 | 水平扩展（多 Worker）+ Hot Reloader + 综合测试 | 生产就绪 |

---

## 22. 附录 A：技术选型与 Pitfalls

**🟢 [SHARED]**

### 22.1 关键 Pitfalls（必须读）

1. **SQLite 不支持 ALTER TABLE DROP COLUMN** — 使用重建表方式迁移（Alembic 自动处理）
2. **MySQL utf8mb4 索引长度限制** — 索引字段用 `String(191)`
3. **异步 ORM 的 Session 隔离** — 每个请求独立 Session，用完关闭
4. **SSE 流式连接管理** — 前端断开时要取消 LLM 请求
5. **钉钉 Stream 长连接心跳** — 每 30 秒发送心跳，断线自动重连
6. **MiniMax 图片URL 需要公网可访问** — 本地文件需先上传到 OSS
7. **设备指纹的持久性** — MAC 地址可伪造，需组合多因子
8. **降解模式的副作用** — 数据库降质必须是可逆的（只 watermark，不损坏原数据）

### 22.2 安装依赖清单

```
# requirements.txt
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
sqlalchemy[asyncio]>=2.0.30
alembic>=1.13.0
asyncpg>=0.29.0          # PostgreSQL
aiosqlite>=0.20.0        # SQLite
aiomysql>=0.2.0          # MySQL
aioodbc>=3.0.0           # SQL Server
cx_oracle>=8.4.0         # Oracle
pyjwt>=2.8.0
cryptography>=42.0
openai>=1.30.0            # LLM 统一 SDK
httpx>=0.27.0
redis>=5.0.0
jinja2>=3.1.0
pydantic>=2.6.0
pydantic-settings>=2.2.0
python-multipart>=0.0.9
weasyprint>=62.0          # POC PDF 生成（可选）
pytest>=8.0
pytest-asyncio>=0.23.0
httpx>=0.27.0
```

---

## 23. 附录 B：Plugin SDK 指南

**🟢 [SHARED] — 提供完整 SDK 供插件开发者使用**

见：`v5.2_PRD.md` 附录 B（Plugin SDK 开发指南，~200 行）

### 23.1 SDK 包含组件

| 组件 | 文件 | 说明 |
|---|---|---|
| 插件基类 | `sdk/plugin_base.py` | 所有插件必须继承 |
| 路由注册 | `sdk/router.py` | FastAPI APIRouter 自动注册 |
| 配置管理 | `sdk/config_manager.py` | §18.8 从 manifest.yaml config 段读取 |
| 数据库 | `sdk/database.py` | 自动获取插件专用数据库 |
| 事件 | `sdk/events.py` | 发布/订阅 EventBus 事件 |
| 多语言 | `sdk/i18n.py` | §18.11 t() 翻译函数 |
| 测试 | `sdk/testing/fixtures.py` | §18.12 pytest fixture 环境 |
| 许可 | `sdk/license.py` | 时间胶囊校验 + 降解模式钩子 |

---

## 文件清单与路径汇总

| 用途 | 本地 LLM 路径 | 云 LLM 路径 | 公共路径 |
|---|---|---|---|
| 🔴 本 PRD | `local-llm/PRD/` | `cloud-llm/PRD/` | `PRD/DDW_AI_Hub_v5.4_MASTER.md` |
| 架构图 | - | - | `PRD/ddw-architecture-platform-only.html` |
| v5.3 补充设计图 | - | - | `PRD/ddw-18x-supplements.html` |
| 定价双轨模型 | - | - | `PRD/ddw-pricing-dual-track.html` |
| 防破解降解模式 | - | - | `PRD/ddw-degradation-mode.html` |
| 生态 4 项补充 | - | - | `PRD/ddw-ecosystem-4additions.html` |
| 试用联调机制 | - | - | `PRD/ddw-trial-and-dev-license.html` |
| 🔴 平台代码 | `local-llm/ddw-ai-hub/` | `cloud-llm/ddw-ai-hub/` | - |
| 🔴 Gitea 仓库 | `http://localhost:3001/chenye/ddw-ai-hub-local` | `http://localhost:3001/chenye/ddw-ai-hub-cloud` | - |
| 🔴 Obsidian 归档 | - | - | `03_项目/统一框架/DDW_AI_Hub_v5.4/` |

---

## 致所有 Agent 开发者

这段 PRD 是 DDW AI Hub Platform 的**唯一需求来源**。

- 无需再读其他文档，这份文档包含了所有必要的需求、规格、架构决定
- 详细代码级参考（如 v5.2 的 EngineFactory 代码、v5.1 的 API 端点和 Provider 实现）已在各章节注明原文档位置，如需完整代码参考请按引用路径打开对应文件
- **所有关键决策**已在这份文档中明确记录，不需要向任何人提问
- 两个 Agent（本地 LLM 和云 LLM）各自独立完成，不存在代码共享

**开始编码。** 🚀
