# TASK_SPEC：知识库引擎 MVP（plugins/ddw_ent_knowledge）v1.0

> 编写：Hermes（2026-08-07）· 执行：MiMo Code（mimo/mimo-v2.5-pro）
> 目标：**今天能演示**的 Flat KB 引擎——上传文档→解析→分块→embedding→向量存储→检索→LLM 问答（SSE 流式），带客服式演示页。
> 背景：两个客户（宋和宋 Dify 慢、祥云化工 Dify 用不好要替换）都需要现场演示 DDW 知识库能力；官网 9cio.com 客服（ddw_online_cs/kb.py）已证明响应速度，本插件把该能力产品化为**通用知识库引擎**。

## 0. 必读材料（动手前先读）

1. `docs/audit_knowledge_base_20260804.md` —— 知识库现状审计（组件复用来源：ddw_bid_writer）
2. `docs/PRD_ddw-knowledge-hierarchy_v1.0.0.md` —— 812 行企业级 PRD（本次只做 Flat MVP，层级检索二期）
3. `plugins/ddw_bid_writer/services/embedding_service.py` —— EmbeddingService ABC + SimpleEmbedding（hash trick + TF-IDF 512 维，零依赖）
4. `plugins/ddw_bid_writer/services/vector_store.py` —— VectorStore + TenantKnowledgeStore（SQLite + JSON embedding 列 + 内存 cosine）
5. `plugins/ddw_bid_writer/services/knowledge_bootstrap.py` —— parse_file + chunk_text（按 ## 标题切块 800-1500 字符）
6. `sdk/plugin_base.py` —— PluginBase 生命周期约定

## 1. 目录与命名（铁律：下划线目录名）

```
plugins/ddw_ent_knowledge/
├── __init__.py            # PLUGIN_NAME + VERSION
├── plugin.py              # Plugin 类（继承 PluginBase），setup() 注册 router
├── router.py              # FastAPI 路由
├── schemas.py             # Pydantic 模型
├── models.py              # ORM：Document / DocumentChunk / SearchLog
├── core/
│   ├── __init__.py
│   ├── embedding.py       # EmbeddingService 抽象 + SimpleEmbedding + OpenAI 兼容 EmbeddingClient
│   ├── vector_store.py    # SQLite + JSON embedding + cosine 搜索（抽自 bid_writer，tenant 隔离）
│   ├── document_parser.py # md/txt/json/yaml 解析 + PDF（pymupdf，扫描件除外）
│   └── chunker.py         # chunk_text 按标题/段落切块（800-1500 字符）
├── services/
│   ├── ingest_service.py  # upload → parse → chunk → embed → write（异步可选，先同步）
│   └── retrieval_service.py # vector top-k + keyword fallback（BM25-lite），可选 LLM rerank
├── templates/
│   └── kb_demo.html       # 演示页：上传 + 聊天式问答 + 检索耗时显示
└── tests/
    ├── test_ingest.py
    ├── test_search.py
    ├── test_parser.py
    └── test_qa.py
```

## 2. 功能范围（MVP）

### 2.1 文档管理 API
- `POST /plugins/ddw-ent-knowledge/documents/upload` —— multipart 上传（md/txt/json/yaml/pdf），自动解析入库
- `GET /plugins/ddw-ent-knowledge/documents` —— 列表（分页）
- `DELETE /plugins/ddw-ent-knowledge/documents/{id}` —— 删除（连带 chunks）

### 2.2 检索 API
- `POST /plugins/ddw-ent-knowledge/search` —— query + top_k；返回 hits（content/score/metadata/took_ms）
- 检索逻辑：向量 cosine top-k（主）+ 关键词 BM25-lite（fallback 兜底），合并去重

### 2.3 问答 API（核心演示能力）
- `POST /plugins/ddw-ent-knowledge/chat` —— 检索 top-5 → 组装 context → 调 LLM 生成 → **SSE 流式返回**（首字 <1s）
- LLM 调用走 `plugins/ddw_llm_gateway`（OpenAI 兼容 /v1/chat/completions），不直连 Provider
- 响应头带 `X-KB-Took-Ms`（检索耗时）——演示页展示"检索 XXms + 生成流式"

### 2.4 Embedding 可插拔（关键设计）
- `EmbeddingService` 抽象：`embed(texts) -> list[list[float]]`
- 实现 1：`SimpleEmbedding`（零依赖兜底，抽自 bid_writer）
- 实现 2：`OpenAICompatEmbedding`（环境变量 `DDW_EMBEDDING_BASE_URL` / `DDW_EMBEDDING_API_KEY` / `DDW_EMBEDDING_MODEL`，默认 `text-embedding-3-small` 兼容格式；国内可用硅基流动 bge-m3 等）
- 未配置 API Key 时自动降级 SimpleEmbedding（保证任何环境能跑通演示）

### 2.5 演示页（templates/kb_demo.html）
- 客服式聊天界面：输入问题 → SSE 流式回答 + 显示"检索耗时 / 总耗时"
- 上传区：拖拽/选择文件 → 入库成功提示 → 立即提问
- 风格：参照 9cio.com 官网客服体验（简洁、快），无需登录

## 3. 技术约束

- FastAPI + SQLAlchemy 2.0（复用 core/database/session.py 的 Base，模型继承 TenantMixin 若有）
- 插件目录结构遵循现有插件惯例（参考 plugins/ddw_online_cs/plugin.py）
- 依赖新增：`pymupdf`（PDF 解析）。**若安装失败，PDF 解析降级为"返回文件名+提示"，md/txt 必须可用**
- 不引入 chromadb/milvus 等重依赖（SQLite 足够 MVP）
- 不做：层级检索/知识桶 ACL/跨文档引用/异步管道（二期）

## 4. 验收标准（全部通过才算完成）

1. `pytest plugins/ddw_ent_knowledge/tests/ -v` 全绿，≥8 条用例：
   - test_ingest：上传 md 文档 → chunks 数量正确、文本完整
   - test_parser：txt/md/pdf（构造简单 PDF）解析成功；非法文件返回 400
   - test_search：入库 3 篇文档 → 语义相近 query 命中正确文档 top1；无匹配时 keyword fallback 有结果
   - test_qa：chat 接口返回 SSE 流（首 chunk 含内容）、X-KB-Took-Ms 头存在
   - test_embedding_fallback：未配置 key 时 SimpleEmbedding 生效（embedding 维度 512）
2. 演示页手测：上传 3 个文档 → 连续问 3 个问题 → 全部有流式回答，检索耗时 <500ms
3. `python -c "from plugins.ddw_ent_knowledge.plugin import Plugin"` 导入无错
4. 现有测试不破坏：`pytest plugins/ -q` 通过（或说明新增前基线）
5. 写 `plugins/ddw_ent_knowledge/README.md`（API 列表 + 演示页用法）

## 5. 提交

- git add plugins/ddw_ent_knowledge/ 后 commit：`feat(kb): 知识库引擎 MVP [LLM: mimo-code]`
- 不提交：.mimocode/、日志、临时文件
