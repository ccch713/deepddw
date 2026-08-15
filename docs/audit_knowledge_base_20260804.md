# DDW AI Hub 知识库(KB)现状审计报告

> **审计日期**：2026-08-04
> **审计范围**：`/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/`
> **审计目标**：识别当前 KB 相关能力、评估与企业级 KB 的差距、给出新建/复用建议

---

## 0. 审计摘要（一句话）

DDW AI Hub **没有统一的"知识库引擎"**，KB 能力**散落在 6 个业务插件**里（cost_knowledge / regulatory_evidence / quality_knowledge / bid_writer / email_assistant 等），每个插件自带小型"事实表"。技术组件（Embedding/VectorStore/Chunker）**仅在 `ddw_bid_writer` 里有零依赖版实现**，未被抽出复用。已有一份 **`PRD_ddw-knowledge-hierarchy_v1.0.0.md`**（812 行）规划了完整的层级 RAG 引擎但**尚未实现**。

---

## 1. 现有能力清单（What Exists）

### 1.1 Core 层（平台底座）

| 模块 | 文件 | 已实现能力 |
|------|------|-----------|
| **KB 权限 API** | `core/api/knowledge.py` | `GET/POST /api/v1/knowledge/bases` + 权限矩阵 CRUD（基于内存字典，硬编码 8 类知识库目录：公共/CS/财务/RD/采购/高管/销售/设备） |
| **MCP 工具** | `core/mcp/tools.py` | 注册 1 个 KB 相关工具：`ddw.kb.search`（**当前为 stub**，返回 `"[stub KB] 检索 q 返回 0 条结果"`）|
| **MCP 资源** | `core/mcp/resources.py` | 注册资源 `ddw://knowledge-bases`（静态硬编码 JSON）|
| **Agent 权限** | `core/services/agent_permission.py` | 三层分级（SAFE/NORMAL/DANGEROUS）+ 会话级白名单 + 审计。`SAFE_TOOLS` 已将 `ddw.kb.search` 列入 |
| **LLM 转发** | `plugins/ddw-llm-gateway/relay.py` | OpenAI 兼容 `/v1/chat/completions` + 多渠道负载均衡 + 熔断 + 流处理 |
| **Embedded LLM** | `plugins/embedded_llm/engine.py` | Local echo backend stub + `chat()`/`embed()` 接口（embed 返回 384 维零向量！） |
| **主入口** | `core/main.py` | 路由挂载：knowledge_router(auth/admin/knowledge/user 四类) + MCP info/jsonrpc/sse + 静态前端 |
| **核心 DB 模型** | `core/database/models.py` | Tenant/User/TokenQuota/ApiKey/TrainingSession/TrainingAssessment/UserBinding — **无任何 KB 表** |

### 1.2 业务插件层 KB 现状（6 个 KB 插件，每个自带"事实表"）

| 插件 | 路由前缀 | ORM 模型 | 检索方式 | 文档数 | 状态 |
|------|---------|---------|---------|--------|------|
| `ddw-cost-knowledge` | `/api/v1/plugins/ddw-cost-knowledge` | `CostDocument` + `CostEstimate`（**强结构化字段**：file_name/total_cost/area/unit_price/project_type）| **BM25-lite 关键词打分**（`search_service.py`：中英 bigram + 字段匹配）| 10 个 API | ✅ 健康 |
| `ddw-regulatory-evidence` | `/api/v1/plugins/ddw-regulatory-evidence` | `RegulatoryDocument` + `EvidenceChain`（**法规 + 证据链**，合规审计方向）| **SQL `ILIKE` 全文搜索**（`or_(title.ilike, content.ilike, ref_num.ilike)`）| 12 个 API | ✅ 健康 |
| `ddw-quality-knowledge` | `/api/v1/plugins/ddw-quality-knowledge` | `KnowledgeDocument` + `SearchLog` | **关键词 ILIKE + LLM rerank**（`semantic_search()`） | 文档/检索双 API | ✅ 健康但目录混乱（`plugins/` 和根 `ddw_quality_knowledge/` 两个版本）|
| `ddw-bid-writer` | `/api/v1/plugins/ddw-bid-writer` | `KnowledgeDocument` + `KnowledgeBootstrapRun` + `FactTemplate` | ⭐ **完整能力**：Embedding + VectorStore + Bootstrap + 分块 + Fact 抽取 | 27 个 API | ✅ **最强 KB 能力拥有者** |

### 1.3 关键技术资产（藏在 ddw_bid_writer 中）

| 组件 | 文件 | 能力 | 可复用性 |
|------|------|------|---------|
| **EmbeddingService 抽象** | `plugins/ddw_bid_writer/services/embedding_service.py` | ABC 接口 + `SimpleEmbedding`（hash trick + TF-IDF，512 维，零依赖）| ⭐ **已可抽出复用** |
| **VectorStore** | `plugins/ddw_bid_writer/services/vector_store.py` | SQLite + JSON embedding 列 + **内存 cosine 搜索** + 1-10 万 chunks 规模 + 线程锁 | ⭐ **已可抽出复用** |
| **TenantKnowledgeStore** | `同上` | 租户级封装 + sync/async 双接口 + metadata filter | ⭐ **已可抽出复用** |
| **KnowledgeBootstrap** | `plugins/ddw_bid_writer/services/knowledge_bootstrap.py` | 文件夹遍历 + 解析（md/txt/json/yaml/yml）+ `chunk_text()`（按 ## 标题切块，800-1500 字符）+ 模板抽取 | ⭐ **已可抽出复用**（除 PDF/DOCX 需补依赖）|
| **Embedding 占位** | `plugins/embedded_llm/engine.py:EmbeddedLLM.embed` | 返回 384 维零向量（**stub**）| ⚠️ 仅 stub |

### 1.4 已规划但未实现的资产

| 文件 | 内容 | 状态 |
|------|------|------|
| `docs/PRD_ddw-knowledge-hierarchy_v1.0.0.md` | **完整 812 行 PRD**：文档→章节→页面→摘要四级层级索引 + 三阶段 RAG（导航→精检→结构化回答）+ 知识桶 ACL + 跨文档引用图谱 + 检索日志 | 📋 仅有设计，未编码 |
| `docs/research/repos/LangBot/.../vector/vdbs/{chroma,pgvector_db,milvus,qdrant,seekdb,valkey_search}.py` | 6 种向量数据库的 LangBot 实现 **（仅作研究参考，未集成）** | 📚 调研材料 |

### 1.5 安装/部署

- `requirements.txt`：**无任何 docx/pdf/embedding 库**（无 PyMuPDF、python-docx、sentence-transformers、chromadb 等）
- `install.sh`：DDW 一键安装（未审计细节）

---

## 2. 缺失能力清单（What's Missing）

### 2.1 与企业级 KB 的差距（按重要性排序）

| # | 缺失能力 | 当前替代品 | 重要性 | 备注 |
|---|---------|----------|--------|------|
| **M1** | **统一 KB 抽象层** | 6 个插件各自造轮子（事实表+CRUD+搜索） | 🔴 P0 | 阻碍任何"跨业务知识检索" |
| **M2** | **正式文档解析管道**（PDF/DOCX 表格+图片提取） | `bid_writer` 只支持 md/txt/json/yaml；`cost_knowledge` 只接 base64 二进制不解内容 | 🔴 P0 | PRD 规划 PyMuPDF + python-docx，未实现 |
| **M3** | **真实 Embedding 模型集成**（BGE-M3 / OpenAI text-embedding-3） | 只有 SimpleEmbedding（hash trick）质量有限 | 🔴 P0 | `requirements.txt` 无 sentence-transformers/openai |
| **M4** | **真实向量数据库**（pgvector / chroma / milvus） | SQLite + JSON 列 + 内存 cosine（10万 chunks 上限） | 🔴 P1 | PRD 兼容性矩阵：PG pgvector 是生产推荐 |
| **M5** | **RAG 三阶段检索**（导航→精检→结构化回答） | 各插件都是 flat chunking，无层级 | 🟡 P1 | 已在 PRD 中设计 |
| **M6** | **知识桶 + ACL 权限模型** | 当前只有 `_visible_categories(role)` 内存表 | 🟡 P1 | PRD 设计 `KnowledgeBucket` |
| **M7** | **文档→章节→页面 树结构** | 无任何层级索引 | 🟡 P1 | PRD 设计 `DocumentTreeNode` |
| **M8** | **跨文档引用图谱** | 无 | 🟢 P2 | PRD 设计 `CrossDocumentReference` |
| **M9** | **检索日志 + 调试面板** | 只有 `ddw_quality_knowledge` 有 SearchLog | 🟢 P2 | PRD 设计 `SearchQueryLog` |
| **M10** | **文档生成模板**（Markdown/HTML/DOCX 输出） | 各插件只存原文，无生成模板；`bid_writer` 有 `templates/bid_writer.html` 但只用于前端 | 🟢 P2 | 无 jinja2/docx 引擎 |
| **M11** | **异步索引管道**（上传→后台解析→embedding→可用通知） | 所有插件都是同步处理 | 🟡 P1 | PRD 设计事件 `knowledge.document.indexed` |
| **M12** | **MCP `ddw.kb.search` 真实现** | 当前 stub 返回 0 结果 | 🔴 P0 | 需绑定统一引擎 |
| **M13** | **多租户向量隔离** | `TenantKnowledgeStore` 已隔离（按租户分 SQLite 文件） | ✅ 已实现 |
| **M14** | **检索评估框架**（用户反馈循环 / hallucination rate） | 无 | 🟢 P3 | PRD quality.ai_output.max_hallucination_rate=0.05 留空 |

### 2.2 代码/工程层缺陷

- **重复造轮子**：每个业务插件都自己实现 `service.py`（CRUD + ILIKE 搜索 + LLM rerank）
- **依赖未声明**：`ddw_quality_knowledge`(根目录版) 是 v1 旧版，新版应在 `plugins/`；regulatory_evidence 也是双套
- **无租户感知的 KB API**：`core/api/knowledge.py` 是内存字典，多租户场景失效
- **无插件级 KB 权限**：所有插件通用 `__tenant_aware__`，无 bucket-level ACL
- **MCP stub 未替换**：核心 `ddw.kb.search` 仍是占位符
- **缺少测试**：`plugins/ddw-cost-knowledge/` 和 `ddw_quality_knowledge/` 有 `tests/`；`ddw-regulatory-evidence/` 也有；但 KB API 端、Embedding、VectorStore 无单测（`bid_writer` 有 `test_cdef_pipeline.py`）

---

## 3. 可复用组件清单（What to Reuse）

### 3.1 直接搬可用（业务代码 100% 兼容）

| 来源 | 路径 | 复用到新插件的成本 |
|------|------|------------------|
| `ddw_bid_writer/services/embedding_service.py` | EmbeddingService ABC + SimpleEmbedding + IDF fit 接口 | 📦 复制到 `plugins/ddw-enterprise-kb/core/embedding.py`，加 BGE/OpenAI 实现 |
| `ddw_bid_writer/services/vector_store.py` | VectorStore + TenantKnowledgeStore（按租户隔离 SQLite）| 📦 升级为可插拔 VDB 后端 |
| `ddw_bid_writer/services/knowledge_bootstrap.py` | parse_file + chunk_text + 模板抽取 | 📦 升级 PDF/DOCX 解析器，提到新插件根目录 |
| `ddw_bid_writer/services/fact_sheet.py` | extract_dates / extract_metrics / extract_personnel | 📦 保留为通用 Fact 抽取工具 |
| `ddw_bid_writer/models.py` | KnowledgeDocument + KnowledgeBootstrapRun + FactTemplate | 📦 复用 schema，改名 |
| `ddw_quality_knowledge/services.py::semantic_search` | keyword → LLM rerank 两段式 | 📦 保留作为 KB 插件 fallback 模式 |

### 3.2 平台能力复用

| 来源 | 能力 | 集成方式 |
|------|------|---------|
| `core/services/agent_permission.py` | 三层权限分级 + SAFE_TOOLS 列表 | 把新 KB 工具注册到 `SAFE_TOOLS` |
| `core/mcp/server.py` + `tools.py` | MCP 工具/资源注册 | 注册 `ddw.kb.search` 真实现 + `ddw://knowledge-buckets` |
| `core/database/tenant_filter.py` | 自动 tenant_id 过滤 | 新 KB 表继承 `TenantMixin` |
| `core/database/session.py::Base` | SQLAlchemy 2.0 DeclarativeBase | 新模型继承 |
| `plugins/ddw-llm-gateway/` | LLM 调用 | 所有 LLM 提炼/摘要走 Gateway，不直连 Provider |
| `plugins/embedded_llm/engine.py` | 本地兜底 LLM + embed | 替换零向量 stub |
| `sdk/plugin_base.py` | PluginBase + lifecycle FSM + ExecutionTrace + InterventionHooks | 新插件继承 |
| `sdk/tool_def.py` | 工具定义工具 | 用于注册 KB 工具的 schema |
| EventBus（`core/events/`）| 跨插件事件总线 | 上传完成触发 `knowledge.document.indexed` |

### 3.3 模板/启发可借鉴

| 文件 | 可借鉴点 |
|------|---------|
| `docs/PRD_ddw-knowledge-hierarchy_v1.0.0.md` | **蓝图**：4 级树、3 阶段检索、知识桶 ACL、跨文档引用、检索日志 |
| `docs/research/repos/LangBot/src/langbot/pkg/vector/vdbs/{chroma,pgvector_db,milvus,qdrant,seekdb,valkey_search}.py` | **多 VDB 适配器参考实现**（6 种） |
| `docs/research/repos/ragflow/agent/templates/ingestion_pipeline_general.json` | **摄取管道 JSON Schema** |
| `docs/research/repos/ragflow/agent/templates/title_chunker.json` | **按标题分块配置** |
| `docs/research/repos/ragflow/memory/utils/{es_conn,ob_conn}.py` | **生产级 VDB 客户端封装** |

---

## 4. 需要新建的组件（What to Build）

### 4.1 核心：新插件 `ddw-enterprise-kb`（建议名称）

```
plugins/ddw-enterprise-kb/
├── manifest.yaml            # name, version, deps(ddw-llm-gateway)
├── plugin.py                # PluginBase 子类，挂载统一路由
├── __init__.py
├── README.md
├── core/
│   ├── embedding.py         # EmbeddingService + SimpleEmbedding + BgeEmbedding + OpenAIEmbedding
│   ├── vector_db.py         # VectorDB 抽象 + SqliteVectorDB + PgVectorDB(后续) + ChromaVectorDB(后续)
│   ├── document_parser.py   # PdfParser(PyMuPDF) + DocxParser + MdParser + HtmlParser + TxtParser
│   ├── chunker.py           # 按标题/段落/字符切块（800/1500 token 窗口）
│   ├── tree_builder.py      # 文档→章节→页面→段落 树构建
│   ├── summary_builder.py   # 自底向上 LLM 摘要（PRD §3.3）
│   └── search_engine.py     # 三阶段检索（导航 LLM → 向量精检 → 结构化回答）
├── models/
│   ├── document.py          # Document（kh_documents）
│   ├── tree_node.py         # DocumentTreeNode（kh_tree_nodes）
│   ├── chunk.py             # DocumentChunk（kh_chunks，embedding JSON 列）
│   ├── cross_ref.py         # CrossDocumentReference
│   ├── bucket.py            # KnowledgeBucket + ACL
│   └── search_log.py        # SearchQueryLog
├── services/
│   ├── ingest_service.py    # upload → parse → chunk → embed → write
│   ├── retrieval_service.py # hierarchical_search / flat_search / hybrid_search
│   ├── bucket_service.py    # 知识桶 CRUD
│   └── event_service.py     # 发 knowledge.document.indexed
├── router.py                # 17 个 API（PRD §4.1）
├── schemas.py               # Pydantic models
├── templates/
│   └── kb_admin.html        # 文档管理 + 目录树渲染
└── tests/
    ├── test_parser.py
    ├── test_chunker.py
    ├── test_embedding.py
    └── test_retrieval.py
```

### 4.2 配套待替换/更新的组件

| 文件 | 改动 |
|------|------|
| `core/api/knowledge.py` | 重构：接入 `ddw-enterprise-kb` 服务，替换内存字典；改为租户感知 |
| `core/mcp/tools.py` | 把 `ddw.kb.search` stub 改为转发到新插件的 `hierarchical_search` |
| `core/mcp/resources.py` | 新增 `ddw://knowledge-buckets` 资源（从 `KnowledgeBucket` 读） |
| `core/services/agent_permission.py::SAFE_TOOLS` | 新插件的只读接口加入白名单 |
| `requirements.txt` | 加 `pymupdf>=1.23` `python-docx>=1.1` `beautifulsoup4` `lxml` |
| **6 个 KB 插件** | 化简为只保留业务字段表，文档/检索调用 `ddw-enterprise-kb` |
| `plugins/ddw_bid_writer/services/{embedding,vector_store,knowledge_bootstrap}.py` | 内部调用 `@deprecated`，推荐迁移到新引擎 |

### 4.3 文档/模板（生成侧 P2）

- `core/templates/` 新建 Jinja2 模板：`markdown_report.html.j2` / `compliance_report.docx.j2`（用 python-docx 包出来）
- 或做独立插件 `ddw-enterprise-kb-templates`（受 License 商业插件拆分启发）

---

## 5. 建议的插件名称与目录结构

### 5.1 命名方案（推荐 `ddw-ent-knowledge`，与现有命名风格一致）

| 候选名 | 说明 | 推荐度 |
|--------|------|--------|
| **`ddw-ent-knowledge`** | ent = enterprise，与 PRD 中的"企业级"含义一致 | ⭐⭐⭐ 主推 |
| `ddw-knowledge-hierarchy` | 与已有 PRD 同名 | ⭐⭐ 次选 |
| `ddw-unified-kb` | 表达"统一"意图 | ⭐ 通用但风格不统一 |
| `ddw-kb-engine` | 表达引擎层 | ⭐ 更技术、更准确，但与现有 `ddw-quality-knowledge` / `ddw-regulatory-evidence` 业务命名风格不一致 |

### 5.2 推荐目录

```
plugins/ddw_ent_knowledge/                # 统一规范：下划线
├── manifest.yaml
├── plugin.py
├── core/
├── models/
├── services/
├── router.py
├── schemas.py
├── templates/
│   ├── ent_kb_admin.html                 # 文档/桶/检索管理后台
│   └── ent_kb_search.html                # 检索调试面板
└── tests/
```

> **风格备注**：DDW 现有插件目录命名混用下划线（`ddw_cost_knowledge`）和连字符（`ddw-quality-knowledge`）。`load_plugins()` 用归一化（`replace("_", "-")`）兼容两者。建议优先使用**下划线**（与最新 bid_writer 一致）。

---

## 6. 落地路线图建议

### 阶段 0：基础设施抽提（半周）
- **0.1** 把 `ddw_bid_writer/services/embedding_service.py` 复制到新插件 `core/embedding.py`
- **0.2** 把 `ddw_bid_writer/services/vector_store.py` 复制到 `core/vector_db.py`，抽象化
- **0.3** 把 `ddw_bid_writer/services/knowledge_bootstrap.py::chunk_text` + `parse_file` 抽到 `core/chunker.py` + `core/document_parser.py`
- **0.4** `requirements.txt` 加 `pymupdf` `python-docx` `beautifulsoup4`
- **0.5** 6 个 KB 插件切到新引擎（保留业务字段表），确保向后兼容

### 阶段 1：MVP — Flat KB Engine（1 周）
- **1.1** 实现 5 个 ORM 模型（Document/Chunk/Bucket/SearchLog/CrossRef）
- **1.2** 实现 5 格式解析器（PDF/DOCX/MD/HTML/TXT）
- **1.3** 实现 17 个 API（PRD §4.1 的子集：documents/upload, documents, search/flat, search/hierarchical, buckets, references, index/status）
- **1.4** 接入 `ddw.llm.chat` 通过 `ddw-llm-gateway`（不直连 Provider）
- **1.5** 接入 MCP：替换 `ddw.kb.search` stub + 新增 `ddw://knowledge-buckets`

### 阶段 2：层级检索（2 周）
- **2.1** DocumentTreeNode 模型 + TreeBuilder
- **2.2** SummaryBuilder（自底向上 LLM 摘要）
- **2.3** SearchEngine 三阶段（导航 LLM → 向量精检 → 结构化回答）
- **2.4** 检索日志 + 调试 API

### 阶段 3：生产化（2 周）
- **3.1** PgVector 适配器
- **3.2** BGE-M3 / OpenAI Embedding 适配器
- **3.3** 异步摄取管道（事件驱动 `knowledge.document.indexed`）
- **3.4** 跨文档引用图谱 UI
- **3.5** 用户反馈循环（hallucination rate 监控）

---

## 7. 风险与约束

| 风险 | 应对 |
|------|------|
| **6 个现有 KB 插件强耦合业务字段**，迁移时易破坏现有 API | 先做 Phase 0 抽提，保留各插件的 service 层，新引擎作为"底层" |
| **PgVector 部署依赖 PostgreSQL** | 兼容矩阵：SQLite JSON 阵列为 dev/poc，PG 生产推荐，与 PRD §8.2 一致 |
| **LLM 摘要生成成本高**（每个文档 N 次 LLM 调用） | 摘要分级缓存 + 增量更新 + 离线批处理 |
| **PDF 解析对扫描件无效**（PyMuPDF 不做 OCR） | Phase 4 接入 PaddleOCR/Tesseract |
| **ddw_bid_writer 是 License-LAYERS 强约束插件** | 新引擎作为 Apache-2.0 独立组件；bid_writer 调用新引擎而非内嵌 |
| **PRD 设计的 4 级树对短文档（聊天记录）不适用** | PRD 已预留"自动降级 flat chunking"策略 |

---

## 8. 关键文件索引

### 已审计
- `core/main.py` ✅
- `core/api/knowledge.py` ✅
- `core/mcp/tools.py` ✅
- `core/mcp/resources.py` ✅
- `core/services/agent_permission.py` ✅
- `core/database/models.py` ✅
- `sdk/plugin_base.py` ✅
- `sdk/plugin_state.py` ✅
- `plugins/ddw_cost_knowledge/{plugin,router,models}.py` ✅
- `plugins/ddw_cost_knowledge/services/{extract,import,search}_service.py` ✅
- `plugins/ddw-regulatory-evidence/{models,services,router,main,manifest.yaml}` ✅
- `plugins/ddw_bid_writer/services/{embedding,vector_store,knowledge_bootstrap}.py` ✅
- `plugins/ddw-quality-knowledge/{models,manifest.yaml}` ✅
- `ddw_quality_knowledge/{main,services}.py`（根目录版，重复实现） ✅
- `plugins/embedded_llm/engine.py` ✅
- `plugins/ddw-llm-gateway/relay.py`（首 80 行） ✅
- `requirements.txt` ✅

### 相关 PRD/研究
- `docs/PRD_ddw-knowledge-hierarchy_v1.0.0.md` ✅ 812 行
- `docs/research/repos/LangBot/.../vector/` ✅ 6 个 VDB 适配器
- `docs/research/repos/ragflow/...` ✅ 摄取管道+分块配置

### 未深审计
- `plugins/ddw-llm-gateway/{channel_manager,circuit_breaker,load_balancer,stream_handler}.py`
- `plugins/ddw-smart-cs/`、`plugins/ddw-email-assistant/`、`plugins/ddw-training/` 中可能的 KB 引用
- `plugins/ddw-cost-knowledge/services/estimate_service.py`
- `frontend/` 中 KB 相关 UI 页面

---

*本审计报告基于 2026-08-04 当日代码状态。建议下游决策时同步核对上述文件最新状态。*
