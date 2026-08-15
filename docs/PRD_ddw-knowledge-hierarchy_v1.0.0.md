# PRD：ddw-knowledge-hierarchy（层级知识检索引擎）v1.0.0

> 灵感来源：StaffDeck 的"文档结构感知的知识检索"概念（AGPL-3.0），DDW 为全新 Apache 2.0 实现
> 创建日期：2026-07-31
> 依赖：ddw-llm-gateway
> 兼容：ddw-ent-knowledge、ddw-cs-knowledge（增强模式，非替代）
> 许可证：Apache 2.0

---

## 零、产品概述

### 0.1 一句话定位

**ddw-knowledge-hierarchy** 将企业文档自动解析为"文档→章节→页面→摘要"四级层级索引，让 AI 先判断信息在哪一层，再逐层定位原文，解决传统 RAG flat chunking 的"大海捞针"问题。

### 0.2 核心创新：从 Flat Chunking 到 Hierarchical Retrieval

```
传统 RAG（Flat Chunking）：
  用户问题 → embedding → cosine similarity → Top-K chunks → LLM 回答
  问题：chunk 缺乏结构上下文，"第3页的表格"和"附录的表格" embedding 相似但含义完全不同

层级检索（Hierarchical Retrieval）：
  用户问题 → LLM 判断"信息可能在哪个层级" → 在该层级内精确搜索 → 逐层下钻 → 定位原文 → LLM 回答
  优势：先导航后搜索，上下文完整，来源可精确引用到"第X章第Y节第Z页"
```

### 0.3 解决的痛点

| 痛点 | 现有方案 | ddw-knowledge-hierarchy 方案 |
|:-----|:---------|:---------------------------|
| 检索结果"看起来相关实际不对" | 靠 chunk 相似度 | 先判断文档章节上下文，再在该章节内搜索 |
| 无法精确引用来源 | "根据知识库..." | "根据《员工手册》第3章第2节第15页..." |
| 长文档检索效果差 | 100页 PDF 被切成 200 个 chunk | 按目录结构索引，定位到具体章节 |
| 多文档交叉引用困难 | 每个文档独立索引 | 跨文档知识图谱 + 层级导航 |

---

## 一、架构设计

### 1.1 整体检索流程

```
┌──────────────┐
│  用户问题     │
│ "年假如何    │
│  计算？"     │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Phase 1: 层级导航（LLM）             │
│                                      │
│  输入：问题 + 文档树摘要              │
│  输出：最可能的相关节点列表           │
│  如：[{文档: "员工手册", 章: "第3章  │
│         休假制度", 节: "3.2 年假"}]   │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│  Phase 2: 层级内精确检索（Vector）     │
│                                      │
│  在选定的章节范围内做 embedding 搜索  │
│  返回：Top-K 相关片段 + 完整上下文    │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│  Phase 3: 结构化回答（LLM）           │
│                                      │
│  输入：问题 + 精确检索结果 + 层级位置 │
│  输出：带来源引用的结构化回答          │
│  "根据《员工手册》第3章第2节，        │
│   您的年假为..."                      │
└──────────────────────────────────────┘
```

### 1.2 与传统 RAG 的兼容

- **非替代关系**：本插件是 ddw-ent-knowledge / ddw-cs-knowledge 的**增强层**，不是替代
- **共存模式**：同一份文档可以同时建 flat index（快速模糊搜索）+ hierarchy index（精确结构化搜索）
- **自动降级**：如果文档没有目录结构（如纯文本聊天记录），自动降级为 flat chunking

---

## 二、数据模型（SQLAlchemy ORM）

### 2.1 核心实体
> **SQLAlchemy 2.0 迁移说明**：以上 ORM 模型展示的是设计意图。代码实现时必须使用 `Mapped[type]` + `mapped_column()` 语法（SQLAlchemy 2.0），参考 `DDW_Plugin_Development_Guide.md` §5.1。


```python
# models.py

import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, DateTime, Integer, Float,
    ForeignKey, JSON, Boolean, Index
)
from sqlalchemy.orm import relationship, declarative_base
from pgvector.sqlalchemy import Vector  # PostgreSQL, SQLite 用 JSON 替代

Base = declarative_base()

# ─── Document (文档主表) ───

class Document(Base):
    __tablename__ = 'kh_documents'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(512), nullable=False, index=True)
    file_path = Column(String(1024), nullable=True)  # 源文件路径
    file_type = Column(String(32), nullable=True)  # pdf | docx | md | txt | html
    file_hash = Column(String(64), nullable=True, index=True)  # SHA256，去重
    file_size = Column(Integer, nullable=True)  # 字节
    
    # 元数据
    author = Column(String(256), nullable=True)
    created_date = Column(DateTime, nullable=True)
    source = Column(String(256), nullable=True)  # 来源（如"公司内部Wiki"）
    tags = Column(JSON, nullable=True)
    
    # 索引状态
    hierarchy_indexed = Column(Boolean, default=False)  # 层级索引已构建
    vector_indexed = Column(Boolean, default=False)     # 向量索引已构建
    
    # 知识桶
    knowledge_bucket = Column(String(128), nullable=True, index=True)  # "HR"/"技术"/"合规"
    
    # 权限
    access_level = Column(String(32), default='internal')  # public | internal | restricted
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    tree = relationship('DocumentTreeNode', back_populates='document',
                       uselist=False, foreign_keys='DocumentTreeNode.document_id')
    chunks = relationship('DocumentChunk', back_populates='document')

    __table_args__ = (
        Index('idx_kh_doc_bucket', 'knowledge_bucket'),
        Index('idx_kh_doc_hash', 'file_hash'),
    )

# ─── DocumentTreeNode (文档树节点) ───

class DocumentTreeNode(Base):
    """
    自引用树结构，每行是一个节点。
    层级：document > chapter > section > page > paragraph
    """
    __tablename__ = 'kh_tree_nodes'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey('kh_documents.id'), nullable=False, index=True)
    parent_id = Column(String(36), ForeignKey('kh_tree_nodes.id'), nullable=True, index=True)
    
    # 节点信息
    node_type = Column(String(32), nullable=False)
    """
    node_type 层级（从高到低）：
    - document_root: 文档根节点（1个/文档）
    - part: 部/篇（大型文档）
    - chapter: 章
    - section: 节
    - subsection: 小节
    - page: 页面（PDF 的物理页）
    - paragraph: 段落
    - table: 表格
    - figure: 图表
    - footnote: 脚注
    """
    
    title = Column(String(512), nullable=True)  # 节点标题（如"第3章 休假制度"）
    node_number = Column(String(64), nullable=True)  # 编号（如"3.2.1"）
    
    # 摘要（LLM 生成，用于层级导航）
    summary = Column(Text, nullable=True)
    """
    每个非叶子节点有一个 LLM 生成的摘要。
    摘要用于 Phase 1 的层级导航——LLM 先扫描所有章节摘要，判断信息最可能在哪个章节。
    """
    
    # 排序
    order_index = Column(Integer, nullable=False)
    
    # 内容范围（指向 DocumentChunk 的范围）
    content_start_chunk_id = Column(String(36), ForeignKey('kh_chunks.id'), nullable=True)
    content_end_chunk_id = Column(String(36), ForeignKey('kh_chunks.id'), nullable=True)
    
    # 元数据
    page_number = Column(Integer, nullable=True)  # PDF 页码
    metadata = Column(JSON, nullable=True)  # 扩展元数据
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    document = relationship('Document', back_populates='tree')
    parent = relationship('DocumentTreeNode', remote_side=[id], backref='children')
    
    __table_args__ = (
        Index('idx_kh_tree_doc_parent', 'document_id', 'parent_id'),
        Index('idx_kh_tree_doc_type', 'document_id', 'node_type'),
    )

# ─── DocumentChunk (文档片段) ───

class DocumentChunk(Base):
    __tablename__ = 'kh_chunks'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey('kh_documents.id'), nullable=False, index=True)
    tree_node_id = Column(String(36), ForeignKey('kh_tree_nodes.id'), nullable=True, index=True)
    
    # 内容
    content = Column(Text, nullable=False)  # 原始文本
    content_hash = Column(String(64), nullable=True)  # SHA256，去重
    
    # Token 统计
    token_count = Column(Integer, nullable=True)  # 用于控制检索窗口
    
    # 向量（PostgreSQL pgvector 或 JSON fallback for SQLite）
    embedding = Column(JSON, nullable=True)  # 开发环境用 JSON 数组，生产用 pgvector
    
    # 排序
    chunk_index = Column(Integer, nullable=False)  # 在文档中的位置
    
    # 元数据
    page_number = Column(Integer, nullable=True)
    is_table = Column(Boolean, default=False)
    is_figure = Column(Boolean, default=False)
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    document = relationship('Document', back_populates='chunks')
    tree_node = relationship('DocumentTreeNode', foreign_keys=[tree_node_id])

    __table_args__ = (
        Index('idx_kh_chunk_doc_index', 'document_id', 'chunk_index'),
        Index('idx_kh_chunk_node', 'tree_node_id'),
    )

# ─── CrossDocumentReference (跨文档引用) ───

class CrossDocumentReference(Base):
    """
    跨文档引用关系。用于构建知识图谱。
    如：《员工手册》第3章引用了《劳动法》第45条
    """
    __tablename__ = 'kh_cross_refs'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_document_id = Column(String(36), ForeignKey('kh_documents.id'), nullable=False)
    source_chunk_id = Column(String(36), ForeignKey('kh_chunks.id'), nullable=True)
    target_document_id = Column(String(36), ForeignKey('kh_documents.id'), nullable=False)
    target_chunk_id = Column(String(36), ForeignKey('kh_chunks.id'), nullable=True)
    
    ref_type = Column(String(32), nullable=False)  # cites | supplements | contradicts | relates_to
    confidence = Column(Float, default=1.0)  # LLM 判断的置信度
    description = Column(Text, nullable=True)  # 引用关系描述
    
    created_at = Column(DateTime, default=datetime.utcnow)

# ─── SearchQueryLog (检索日志，用于调试和改进) ───

class SearchQueryLog(Base):
    __tablename__ = 'kh_search_logs'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    query = Column(Text, nullable=False)
    
    # Phase 1 结果
    navigation_result = Column(JSON, nullable=True)
    """LLM 导航结果：
    [{"tree_node_id": "xxx", "title": "第3章 休假制度", "confidence": 0.92, "reasoning": "问题涉及年假计算"}]
    """
    
    # Phase 2 结果
    retrieval_result = Column(JSON, nullable=True)
    """精确检索结果：
    [{"chunk_id": "yyy", "score": 0.95, "content_preview": "年假天数按..."}]
    """
    
    # 最终回答
    final_answer = Column(Text, nullable=True)
    sources_cited = Column(JSON, nullable=True)
    
    # 用户反馈
    user_rating = Column(Integer, nullable=True)  # 1-5
    user_feedback_text = Column(Text, nullable=True)
    
    # Token 消耗
    navigation_tokens = Column(Integer, nullable=True)
    retrieval_tokens = Column(Integer, nullable=True)
    answer_tokens = Column(Integer, nullable=True)
    
    # 耗时
    navigation_duration_ms = Column(Integer, nullable=True)
    retrieval_duration_ms = Column(Integer, nullable=True)
    answer_duration_ms = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_kh_log_created', 'created_at'),
    )

# ─── KnowledgeBucket (知识桶) ───

class KnowledgeBucket(Base):
    __tablename__ = 'kh_buckets'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(128), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    
    # 权限
    access_roles = Column(JSON, nullable=True)  # ["admin", "hr_manager"]
    
    created_at = Column(DateTime, default=datetime.utcnow)
```

---

## 三、文档解析管道

### 3.1 支持的文件格式

| 格式 | 解析方式 | 结构提取 | 表格提取 | 图片提取 |
|:-----|:---------|:---------|:---------|:---------|
| PDF | PyMuPDF (fitz) | 目录 + 标题字体/大小推断 | ✅ | ✅（截图存为描述） |
| DOCX | python-docx | 标题样式 (Heading 1-9) | ✅ | ✅（替代文本） |
| Markdown | mistletoe | # → H1, ## → H2 | ✅ (GFM tables) | ❌ |
| HTML | BeautifulSoup | h1-h6 标签 | ✅ | ✅（alt 文本） |
| TXT | 正则 + LLM | LLM 推断结构 | ❌ | ❌ |

### 3.2 解析管道流程

```
┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ 文件上传  │───→│ 格式检测     │───→│ 结构解析     │───→│ Chunk 分割   │
│          │    │ (MIME type) │    │ (目录+标题)  │    │ (500-1000字) │
└──────────┘    └──────────────┘    └──────┬───────┘    └──────┬───────┘
                                           │                   │
                                           ▼                   ▼
                                    ┌──────────────┐    ┌──────────────┐
                                    │ 树构建       │    │ Embedding     │
                                    │ (TreeNode)   │    │ (向量化)     │
                                    └──────┬───────┘    └──────┬───────┘
                                           │                   │
                                           ▼                   ▼
                                    ┌──────────────┐    ┌──────────────┐
                                    │ 摘要生成     │    │ 索引写入     │
                                    │ (LLM 逐章)   │    │ (SQLite/PG)  │
                                    └──────┬───────┘    └──────────────┘
                                           │
                                           ▼
                                    ┌──────────────┐
                                    │ 索引就绪     │
                                    │ ✅           │
                                    └──────────────┘
```

### 3.3 摘要生成策略

```python
# pipeline.py (伪代码)

async def generate_summaries(document_id: str):
    """
    自底向上生成摘要。
    先为叶子节点（段落/页面）生成摘要 → 汇聚为父节点（节）摘要 → 汇聚为祖父节点（章）摘要
    """
    tree = await get_document_tree(document_id)
    
    # 从叶子节点开始（最深层级）
    for level in reversed(range(tree.max_depth + 1)):
        nodes_at_level = tree.get_nodes_at_level(level)
        
        for node in nodes_at_level:
            if node.node_type == 'paragraph':
                # 叶子节点：直接取 chunk 内容的前 200 字
                node.summary = node.get_content()[:200]
            else:
                # 非叶子节点：聚合子节点摘要
                children_summaries = [c.summary for c in node.children if c.summary]
                
                if not children_summaries:
                    continue
                
                # LLM 生成聚合摘要
                prompt = f"""你是文档摘要助手。以下是"{node.title}"的子章节摘要，请生成一个简洁的章节摘要（100字以内），用于后续的检索导航。

子章节摘要：
{chr(10).join(f'- {s}' for s in children_summaries)}

请生成"{node.title}"的摘要："""
                
                response = await llm_gateway.chat(prompt)
                node.summary = response.content[:200]
    
    await save_tree(tree)
```

---

## 四、检索 API 端点

### 4.1 端点清单

```python
# router.py

from fastapi import APIRouter, Depends, Query, Path, Body, UploadFile, File
from typing import List, Optional

router = APIRouter(prefix="/api/v1/plugins/ddw-knowledge-hierarchy", tags=["Knowledge Hierarchy"])

# ─── 文档管理 ───

@router.post("/documents/upload", response_model=DocumentSchema, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    knowledge_bucket: str = Body("default"),
    tags: List[str] = Body(default=[]),
    access_level: str = Body("internal"),
    auto_index: bool = Body(default=True, description="上传后自动构建索引"),
    current_user = Depends(get_current_user),
) -> DocumentSchema:
    """
    上传文档。
    支持：PDF, DOCX, MD, HTML, TXT。
    如果 auto_index=True，异步启动索引构建管道。
    """

@router.get("/documents", response_model=List[DocumentSchema])
async def list_documents(
    knowledge_bucket: Optional[str] = Query(None),
    file_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1),
    page_size: int = Query(20),
    current_user = Depends(get_current_user),
) -> PaginatedResponse[DocumentSchema]:
    """列出文档"""

@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str = Path(...)):
    """删除文档及其所有索引数据"""

# ─── 文档树 ───

@router.get("/documents/{document_id}/tree", response_model=TreeSchema)
async def get_document_tree(
    document_id: str = Path(...),
    max_depth: int = Query(3, description="最大展开深度"),
    current_user = Depends(get_current_user),
) -> TreeSchema:
    """获取文档的层级树结构（用于前端渲染目录导航）"""

@router.get("/documents/{document_id}/nodes/{node_id}/content")
async def get_node_content(
    document_id: str = Path(...),
    node_id: str = Path(...),
    current_user = Depends(get_current_user),
) -> NodeContentSchema:
    """获取某个树节点下的完整内容（合并其所有叶子 chunk）"""

# ─── 层级检索（核心 API） ───

@router.post("/search/hierarchical", response_model=HierarchicalSearchResultSchema)
async def hierarchical_search(
    query: str = Body(..., description="搜索问题"),
    knowledge_buckets: List[str] = Body(default=[], description="限定知识桶"),
    document_ids: List[str] = Body(default=[], description="限定文档"),
    max_navigation_nodes: int = Body(default=5, description="Phase 1 最多返回的导航节点数"),
    max_retrieval_chunks: int = Body(default=10, description="Phase 2 最多返回的 chunk 数"),
    include_summaries: bool = Body(default=True, description="是否在结果中包含层级摘要"),
    search_mode: str = Body(default="hierarchical",
                           description="hierarchical | flat | hybrid"),
    current_user = Depends(get_current_user),
) -> HierarchicalSearchResultSchema:
    """
    层级检索——核心 API。
    
    三阶段流程：
    Phase 1 (导航)：LLM 扫描文档树摘要 → 判断信息在哪些章节
    Phase 2 (精确检索)：在选定章节内做向量搜索
    Phase 3 (回答)：LLM 结合检索结果生成结构化回答
    
    search_mode:
    - hierarchical: 完整三阶段（默认，最准确）
    - flat: 跳过 Phase 1，直接用向量搜索（传统 RAG，快速但不精确）
    - hybrid: Phase 1 + Phase 2 并行，结果融合（推荐生产使用）
    """

@router.post("/search/flat", response_model=FlatSearchResultSchema)
async def flat_search(
    query: str = Body(...),
    knowledge_buckets: List[str] = Body(default=[]),
    top_k: int = Body(default=10),
    current_user = Depends(get_current_user),
) -> FlatSearchResultSchema:
    """传统 flat chunking 搜索（兼容模式）"""

# ─── 检索调试 ───

@router.get("/search/logs/{log_id}", response_model=SearchLogDetailSchema)
async def get_search_log(
    log_id: str = Path(...),
    current_user = Depends(get_current_user),
) -> SearchLogDetailSchema:
    """
    查看检索日志详情。
    包含：导航判断的 reasoning、每个 chunk 的相似度得分、最终引用的来源。
    用于调试"为什么 AI 没有找到正确答案"。
    """

@router.get("/search/logs", response_model=List[SearchLogSchema])
async def list_search_logs(
    document_id: Optional[str] = Query(None),
    user_rating: Optional[int] = Query(None),
    page: int = Query(1),
    current_user = Depends(get_current_user),
) -> PaginatedResponse[SearchLogSchema]:
    """列出检索日志，支持按文档和评分筛选"""

# ─── 知识桶管理 ───

@router.post("/buckets", response_model=BucketSchema, status_code=201)
async def create_bucket(
    name: str = Body(...),
    description: str = Body(None),
    access_roles: List[str] = Body(default=[]),
    current_user = Depends(get_current_user),
) -> BucketSchema:
    """创建知识桶"""

@router.get("/buckets", response_model=List[BucketSchema])
async def list_buckets(current_user = Depends(get_current_user)):
    """列出知识桶"""

# ─── 跨文档引用 ───

@router.get("/documents/{document_id}/references", response_model=List[CrossRefSchema])
async def get_document_references(
    document_id: str = Path(...),
    ref_type: Optional[str] = Query(None),
    current_user = Depends(get_current_user),
) -> List[CrossRefSchema]:
    """获取文档的跨文档引用关系"""

# ─── 索引管理 ───

@router.post("/documents/{document_id}/reindex", status_code=202)
async def reindex_document(
    document_id: str = Path(...),
    full_rebuild: bool = Body(default=False, description="完全重建（True）还是增量更新（False）"),
    current_user = Depends(get_current_user),
):
    """触发文档重新索引"""

@router.get("/index/status", response_model=IndexStatusSchema)
async def get_index_status(current_user = Depends(get_current_user)):
    """获取索引状态（总文档数、总 chunk 数、索引健康度）"""
```

### 4.2 检索结果 Schema

```python
# schemas.py

class NavigationNode(BaseModel):
    """Phase 1 导航结果中的单个节点"""
    tree_node_id: str
    title: str
    node_type: str
    node_number: Optional[str]  # "3.2.1"
    summary: Optional[str]
    confidence: float  # LLM 判断的置信度 0-1
    reasoning: str  # LLM 的判断理由："问题涉及年假计算，该章节标题为'年假制度'"

class RetrievalChunk(BaseModel):
    """Phase 2 精确检索结果中的单个 chunk"""
    chunk_id: str
    content: str
    score: float  # 向量相似度
    tree_node_path: str  # "员工手册 > 第3章 休假制度 > 3.2 年假 > 第15页"
    page_number: Optional[int]
    surrounding_context: Optional[str]  # 前后文

class HierarchicalSearchResult(BaseModel):
    """完整的层级检索结果"""
    query: str
    search_mode: str
    total_duration_ms: int
    
    # Phase 1
    navigation_nodes: List[NavigationNode]
    navigation_duration_ms: int
    navigation_tokens: int
    
    # Phase 2
    retrieval_chunks: List[RetrievalChunk]
    retrieval_duration_ms: int
    
    # Phase 3 (如果 search_mode 为 hierarchical)
    answer: Optional[str]  # LLM 生成的结构化回答
    cited_sources: Optional[List[dict]]  # [{"document": "员工手册", "chapter": "3.2", "page": 15, "excerpt": "..."}]
    answer_duration_ms: Optional[int]
    answer_tokens: Optional[int]
    
    # 日志
    log_id: str  # 用于后续查看调试信息
```

---

## 五、嵌入（Embedding）策略

### 5.1 模型选型

| 模型 | 维度 | 适用场景 | 成本 |
|:-----|:----:|:---------|:-----|
| BGE-M3 (BAAI) | 1024 | 中英文混合，推荐默认 | 免费（本地） |
| text-embedding-3-small (OpenAI) | 1536 | 英文为主 | $0.02/1M tokens |
| m3e-large (Moka AI) | 1024 | 纯中文 | 免费（本地） |

**DDW 默认选择**：BGE-M3（本地 Ollama 或通过 DDW Gateway 调用云端），支持中英文，8192 token 上下文。

### 5.2 Chunk 分割策略

```python
# chunker.py

DEFAULT_CHUNK_SIZE = 800  # tokens
DEFAULT_CHUNK_OVERLAP = 100  # tokens

# 分割优先级：
# 1. 按文档的自然段落边界分割（优先）
# 2. 如果段落超过 chunk_size，按句子边界分割
# 3. 如果句子超过 chunk_size，按 chunk_size 硬截断
# 4. 每个 chunk 记录其 tree_node_id，保持层级关联
```

---

## 六、前端交互设计

### 6.1 文档管理页面

- 文档上传拖拽区（支持批量）
- 文档列表（表格：名称/类型/大小/索引状态/知识桶/上传时间）
- 索引状态指示器（🟢已索引 / 🟡索引中 / 🔴索引失败 / ⚪ 未索引）
- 点击文档 → 展开目录树（左侧）+ 内容预览（右侧）

### 6.2 检索调试面板

- 搜索框 + 知识桶选择器 + 搜索模式切换
- 结果展示：
  - Phase 1 导航理由（可折叠）—— "LLM 认为答案在《员工手册》第3章，因为..."
  - Phase 2 chunk 得分列表（可展开看完整内容）
  - 来源引用高亮
- 反馈按钮（👍/👎 + 文字反馈）
- "为什么没有找到？"调试入口 → 跳转到 SearchLogDetail

---

## 七、性能基准

| 指标 | 目标 | 说明 |
|:-----|:----:|:-----|
| 文档解析速度 | 10页/秒 | PDF 解析+结构提取 |
| 索引构建速度 | 50 chunks/秒 | 含 embedding 生成 |
| 层级导航（Phase 1） | < 2s | LLM 扫描摘要 |
| 精确检索（Phase 2） | < 500ms | 向量搜索 |
| 完整检索（Phase 1+2+3） | < 5s | 端到端 |
| 支持最大文档大小 | 100MB / 2000页 | 单文档 |
| 支持最大知识库大小 | 10,000 文档 / 1,000,000 chunks | 总容量 |

---

## 八、配置与部署

### 8.1 manifest.yaml

```yaml
name: ddw-knowledge-hierarchy
version: 1.0.0
description: "层级知识检索引擎"
author: DDW Team
license: Apache-2.0
engine: ">=2.0.0"
isolation: inline

permissions:
  - "database:ddw_knowledge_hierarchy"
  - "api:ddw-llm-gateway:read"

dependencies:
  plugins:
    ddw-llm-gateway: ">=1.0.0"
  python:
    - fastapi>=0.110
    - sqlalchemy>=2.0
    - pydantic>=2.0
    - PyMuPDF>=1.23

events:
  produces:
    - "knowledge.document.indexed"
    - "knowledge.search.completed"
  consumes: []

config:
  optional:
    embedding_model: "bge-m3"
    embedding_dimensions: 1024
    chunk_size_tokens: 800
    chunk_overlap_tokens: 100
    default_search_mode: "hybrid"
    max_document_size_mb: 100
    navigation_llm_model: "mimo-v2.5-pro"
    answer_llm_model: "mimo-v2.5-pro"

ecosystem:
  category: "core-engine"
  tags: ["knowledge", "rag", "search", "retrieval"]

quality:
  ai_output:
    required: false
    max_hallucination_rate: 0.05
```

### 8.2 兼容性矩阵

| 数据库 | 向量存储 | 状态 |
|:-------|:---------|:----:|
| SQLite | JSON 数组 + 暴力搜索 | ✅ 开发/演示 |
| PostgreSQL + pgvector | Vector 类型 + IVFFlat/HNSW 索引 | ✅ 生产推荐 |
| MySQL | JSON 数组 | ⚠️ 不推荐（无向量索引） |

---



## X. 插件入口（DDW 规范要求）

### register(app) 注册函数

```python
# __init__.py
PLUGIN_NAME = "ddw-knowledge-hierarchy"
PLUGIN_VERSION = "1.0.0"

def register(app, config=None):
    """DDW 平台调用此函数挂载插件路由。"""
    from .router import router
    app.include_router(
        router,
        prefix=f"/api/v1/plugins/{PLUGIN_NAME}",
        tags=[PLUGIN_NAME],
    )
```

### 标准健康检查端点

```python
# router.py 中必须包含
@router.get("/health")
async def health():
    return {
        "plugin": PLUGIN_NAME,
        "status": "ok",
        "version": PLUGIN_VERSION,
        "endpoints": ["/documents", "/search/hierarchical", "/buckets"],
    }
```

### 资源消耗声明（DDW 规范 §5.4）

| 维度 | 评估值 |
|:-----|:------|
| CPU 常态负载 | 5-10% |
| CPU 峰值负载 | 25% |
| 基础内存 | 64 MB |
| 运行时内存 | 128 MB |
| 峰值内存 | 256 MB |
| 代码体积 | 80 KB |
| 数据库存储 | 按使用量 |
| LLM Token | 走 DDW Gateway（不自配 Provider） |
| 必需依赖 | ddw-llm-gateway |
| 资源评级 | **轻量级/中等级** |

## 九、灵感溯源与合规声明

- **灵感来源**：StaffDeck 的"文档结构感知的知识检索"概念——文档→章节→页面→摘要层级索引，先判断信息位置再逐层定位
- **DDW 实现**：全新 Apache 2.0 实现。层级树结构基于文件系统目录树范式，摘要生成采用自底向上 MapReduce 聚合，参考了经典的 RAPTOR（Recursive Abstractive Processing for Tree-Organized Retrieval）论文思路。所有代码完全自主开发
- **差异化**：DDW 的跨文档引用图谱、检索调试面板、hybrid 搜索模式、多知识桶 ACL 权限均为 StaffDeck 不具备的特性

---

*本文档为 PRD 初稿。代码实现由 MiMo Code CLI 执行，DeepSeek V4 Flash 负责代码审查。*
