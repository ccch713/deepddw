# DDW AI Hub · 16G 设备开发任务 Brief

> **由 32G DeepSeek V4 Pro 签发**  
> **执行端**：16G Mac mini + MiniMax M3 + AHE Loop  
> **签发时间**：2026-07-04 01:21  
> **验收端**：32G DeepSeek V4 Pro（不改代码，只验收）  

---

## 🔧 开发铁律

1. **MiniMax M3 API 生成所有代码** — 不允许手动写代码或使用其他 LLM
2. **AHE Loop 自评自修** — 每写完一个文件/模块，立即跑 `propose → eval → fix → verify` 闭环
3. **质量不达标自己修** — 32G 不改作业，只退回重做
4. **所有产物写入 16G 本地** — `/Users/chenye/workspace/ddw-ai-hub/` 和 `/Users/chenye/workspace/ddw-plugins/`
5. **数据库红线**：所有持久化必须用 PostgreSQL，禁止 SQLite

---

## 📦 任务清单（按优先级执行）

### C2 · DDW 嵌入式 LLM 方案（设计 + POC）

**目标**：设计并实现 DDW 平台内置的小微 LLM，随平台一起部署。

**交付物**：
- `ddw-ai-hub/embedded_llm/design.md` — 方案设计（选型对比：llama.cpp vs ONNX vs MLX）
- `ddw-ai-hub/embedded_llm/engine.py` — LLM 引擎封装（统一接口）
- `ddw-ai-hub/embedded_llm/model_manager.py` — 模型下载/缓存/切换
- `ddw-ai-hub/plugins/embedded_llm/` — 作为 DDW 插件封装
- `ddw-ai-hub/embedded_llm/test_engine.py` — 单元测试

**技术约束**：
- 体积 < 2GB（含模型）
- 支持 CPU 推理（断网环境可用）
- 5 个场景：①聊天部署 ②自我修复 ③离线排查 ④升级管理 ⑤插件推荐
- 推荐模型：Qwen2.5-1.5B-Instruct（GGUF Q4_K_M，~1GB）

**接口要求**：
```python
class EmbeddedLLM:
    async def chat(self, prompt: str, system: str = "") -> str
    async def health_check(self) -> dict
    def model_info(self) -> dict  # name, size, loaded
```

---

### C3 · DDW 一键部署脚本

**目标**：让客户在任意 Linux 服务器上一键部署 DDW 平台。

**交付物**：
- `ddw-ai-hub/scripts/deploy.sh` — 一键部署脚本
- `ddw-ai-hub/scripts/deploy.py` — Python 版部署器（推荐，跨平台更好）
- `ddw-ai-hub/config/deployment.yaml.template` — 部署配置模板

**功能要求**：
1. 自动检测 OS（Ubuntu/Debian/CentOS/macOS）
2. 自动安装依赖（Python 3.10+, PostgreSQL, Caddy/Nginx）
3. 自动创建数据库、用户、表
4. 自动配置 systemd/launchd 服务
5. 支持 `--dry-run` 预检查模式
6. 支持 `--plugins=operations,knowledge-base` 选择性部署插件

---

### D · DDW 运营插件（4 个模块）

**目标**：OPC 一人公司的自动化运营中台。

**交付物**：
- `ddw-plugins/operations/manifest.yaml` + `__init__.py`
- `ddw-plugins/operations/content_marketing.py` — 内容营销（博客/公众号/SEO 文章生成）
- `ddw-plugins/operations/customer_service.py` — 客服路由（FAQ 匹配 + 升级人工）
- `ddw-plugins/operations/email_handler.py` — 邮件处理（IMAP 收件 → 分类 → 自动回复）
- `ddw-plugins/operations/seo_monitor.py` — SEO 监控（排名跟踪 + 建议）
- `ddw-plugins/operations/tests/` — 每个模块 3+ 测试

**每个模块的 API**：
```python
# content_marketing
POST /api/v1/plugins/operations/content/generate  — 生成文章
GET  /api/v1/plugins/operations/content/articles   — 文章列表

# customer_service  
POST /api/v1/plugins/operations/support/query      — 客户咨询
GET  /api/v1/plugins/operations/support/history     — 历史记录

# email_handler
POST /api/v1/plugins/operations/email/fetch         — 拉取邮件
POST /api/v1/plugins/operations/email/reply         — 自动回复模板

# seo_monitor
POST /api/v1/plugins/operations/seo/check           — 检查排名
GET  /api/v1/plugins/operations/seo/report          — SEO 周报
```

**注意**：email_handler 无需真正发邮件——定义接口 + 返回模板即可；实际发邮件走外部 SMTP 服务。

---

### E · DDW 知识库插件

**目标**：从 Obsidian Vault 同步到 PostgreSQL，供 DDW 平台内检索。

**交付物**：
- `ddw-plugins/knowledge-base/manifest.yaml` + `__init__.py`
- `ddw-plugins/knowledge-base/sync.py` — Obsidian → PG 同步引擎
- `ddw-plugins/knowledge-base/search.py` — 全文搜索 + 语义搜索
- `ddw-plugins/knowledge-base/indexer.py` — 增量索引
- `ddw-plugins/knowledge-base/tests/` — 测试

**功能要求**：
1. 扫描 Obsidian Vault（`~/Documents/Obsidian Vault/`）Markdown 文件
2. 解析 YAML frontmatter + wikilinks + 标签
3. 写入 PostgreSQL（tenant 隔离，每个租户只看自己的知识库）
4. 支持增量同步（mtime 检测，只更新变化的文件）
5. 全文搜索 API（pg_trgm + tsvector）

**API**：
```python
POST /api/v1/plugins/knowledge-base/sync      — 触发同步
GET  /api/v1/plugins/knowledge-base/search?q=  — 搜索
GET  /api/v1/plugins/knowledge-base/stats      — 统计信息
```

---

### F · ruiguo 改造为 DDW 插件

**目标**：将现有 ruiguo 项目（`/Users/chenye/workspace/ruiguo/`）改造为 DDW 标准插件。

**交付物**：
- `ddw-plugins/ruiguo/manifest.yaml` + `__init__.py`
- `ddw-plugins/ruiguo/pages.py` — 锐果官网页面路由
- `ddw-plugins/ruiguo/products.py` — 产品展示 API
- `ddw-plugins/ruiguo/tests/` — 测试

**改造要点**：
1. 保留 ruiguo 原有页面和逻辑
2. 包装为 DDW 插件（`register(app)` 入口）
3. 数据库从 ruiguo 独立库迁移到 DDW PostgreSQL
4. 保持 www.9cio.com 路由兼容
5. 添加 `/api/v1/plugins/ruiguo/health` 健康检查

**参考**：ruiguo 源码在 `32G:/Users/chenye/workspace/ruiguo/`，需要从 32G scp 到 16G。

---

### G · 16G 飞书多 Agent 方案

**目标**：在 16G 上配置飞书 app，使多个 Agent 能独立收发飞书消息。

**交付物**：
- `ddw-plugins/feishu-multi-agent/manifest.yaml` + `__init__.py`
- `ddw-plugins/feishu-multi-agent/dispatcher.py` — 消息路由（按关键词/用户 → 对应 Agent）
- `ddw-plugins/feishu-multi-agent/agent_registry.py` — Agent 注册表
- `ddw-plugins/feishu-multi-agent/tests/` — 测试

**需求**：
1. 一个飞书 App 支持多个"虚拟 Agent"（如客服 Agent、销售 Agent、技术支持 Agent）
2. 根据消息关键词或用户身份路由到不同 Agent
3. Agent 注册表支持热更新（不重启服务）
4. 每个 Agent 可配置独立的 system prompt

**API**：
```python
POST /api/v1/plugins/feishu-multi-agent/webhook  — 飞书回调入口
GET  /api/v1/plugins/feishu-multi-agent/agents    — Agent 列表
POST /api/v1/plugins/feishu-multi-agent/agents    — 注册/更新 Agent
```

---

## 🔄 AHE Loop 自评流程（每个任务必须走）

```bash
# 1. 初始化 AHE Loop（每个插件目录）
cd /Users/chenye/workspace/ddw-plugins/<plugin-name>
mkdir -p .ahe-loop
cp ~/.hermes/skills/opentracy-ahe-loop/scripts/ahe-loop.py .ahe-loop/

# 2. 写完代码后立即评估
python3 .ahe-loop/ahe-loop.py propose --task "<module>" --llm-dirs "."
python3 .ahe-loop/ahe-loop.py eval --candidate-id cand-001
# 如果 verdict = IMPROVE → 修复
python3 .ahe-loop/ahe-loop.py fix --candidate-id cand-001
# 重新评估，直到 verdict = KEEP

# 3. 全部 KEEP 后才标记完成
```

**AHE 评分标准**（DDW 插件专用）：
- py_compile 通过率 = 100%（硬门槛，不通过直接 ROLLBACK）
- ruff --select=E,W,F 警告 ≤ 3
- pytest 覆盖率 ≥ 70%
- API 端点可访问测试全通过
- manifest.yaml 语法正确

---

## 📊 验收标准（32G 审核用）

| 维度 | 标准 | 不通过处理 |
|:--|:--|:--|
| 代码编译 | 100% py_compile 通过 | 退回重做 |
| 代码规范 | ruff ≤ 3 警告 | 退回修复 |
| 测试覆盖 | pytest ≥ 70% 覆盖率 | 退回补充 |
| API 可用 | 所有端点 curl 可达 | 退回修复 |
| manifest | yaml.safe_load 通过 | 退回修复 |
| DB 红线 | 无 SQLite 引用 | 退回重做 |
| AHE 闭环 | verdict = KEEP | 退回完善 |

---

## 📁 16G 文件结构（完成后）

```
/Users/chenye/workspace/
├── ddw-ai-hub/
│   ├── sdk/                    # ✅ 已同步
│   ├── plugins/_template/      # ✅ 已同步
│   ├── config/deployment.yaml  # ✅ 已同步
│   ├── embedded_llm/           # C2 产物
│   └── scripts/deploy.sh       # C3 产物
├── ddw-plugins/
│   ├── operations/             # D 产物
│   ├── knowledge-base/         # E 产物
│   ├── ruiguo/                 # F 产物
│   └── feishu-multi-agent/     # G 产物
```

---

## ⚡ 最后提醒

- **每完成一个文件就跑 AHE eval**，不要堆到最后
- **不要跳过测试**，每个模块 3+ 测试
- **manifest.yaml 是插件身份证**，缺它无法安装
- **32G 不改你的代码**——质量是自己挣的

🎯 开始干活！
