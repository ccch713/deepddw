# TASK_SPEC: 知识库（公司/部门/员工 三层权限）

> 优先级：P1  
> 预计工时：3-5 天  
> 插件名：ddw_knowledge_hierarchy（扩展现有）  
> 状态：待确认

---

## 1. 概述

知识库是 DDW 的文档管理和检索系统，支持三层权限：
- **公司级 KB**：全员可见，由公司管理员管理
- **部门级 KB**：仅部门内可见，由部门管理员管理
- **员工级 KB**：仅本人可见

**核心规则**：
- 员工的 Skill 允许下载，但 Skill 一旦建立在公司层面上不能删除
- 员工主动点"停用"只是停用，不是删除
- 公司和部门层面都能看到所有 Skill，并能分配给数字员工或其他员工

## 2. 数据模型

### 2.1 知识库（KnowledgeBase）

```python
class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    
    id: int = Column(Integer, primary_key=True)
    tenant_id: int = Column(Integer, nullable=False)
    name: str = Column(String(200), nullable=False)
    description: str = Column(Text, default="")
    scope: str = Column(String(20), default="company")   # company / department / personal
    scope_id: int = Column(Integer, nullable=True)        # department_id 或 user_id
    doc_count: int = Column(Integer, default=0)
    chunk_count: int = Column(Integer, default=0)
    status: str = Column(String(20), default="active")
    created_by: int = Column(Integer, nullable=False)
    created_at: datetime = Column(DateTime, default=utcnow)
    updated_at: datetime = Column(DateTime, default=utcnow, onupdate=utcnow)
```

### 2.2 文档（KBDocument）

```python
class KBDocument(Base):
    __tablename__ = "kb_documents"
    
    id: int = Column(Integer, primary_key=True)
    kb_id: int = Column(Integer, ForeignKey("knowledge_bases.id"), nullable=False)
    filename: str = Column(String(500), nullable=False)
    file_type: str = Column(String(20), default="pdf")    # pdf/docx/txt/md/html
    file_size: int = Column(Integer, default=0)
    chunk_count: int = Column(Integer, default=0)
    status: str = Column(String(20), default="indexed")    # indexing / indexed / error
    uploaded_by: int = Column(Integer, nullable=False)
    created_at: datetime = Column(DateTime, default=utcnow)
```

## 3. 权限矩阵

| 操作 | owner | dept admin | member |
|------|-------|-----------|--------|
| 查看公司级 KB | ✅ | ✅ | ✅ |
| 管理公司级 KB（增删文档） | ✅ | ❌ | ❌ |
| 查看本部门 KB | ✅ | ✅ | ✅ |
| 管理本部门 KB | ✅ | ✅ | ❌ |
| 查看自己的 KB | ✅ | ✅ | ✅ |
| 管理自己的 KB | ✅ | ✅ | ✅ |
| 搜索跨层 KB | ✅（全部） | ✅（公司+本部门+自己） | ✅（公司+自己） |

## 4. API 端点

```yaml
GET    /api/v1/kb                                # 知识库列表（按权限过滤）
POST   /api/v1/kb                                # 创建知识库
GET    /api/v1/kb/{id}                           # 详情（含文档列表）
DELETE /api/v1/kb/{id}                           # 删除知识库

POST   /api/v1/kb/{id}/documents                 # 上传文档
DELETE /api/v1/kb/{id}/documents/{doc_id}        # 删除文档

POST   /api/v1/kb/search                         # 跨知识库检索
# body: { query: "xxx", scopes: ["company", "department", "personal"] }
```

## 5. 前端页面

### 5.1 知识库列表（saas-admin.html#/kb）

- 三层 Tab：公司级 / 部门级 / 我的
- 每层：知识库卡片列表（名称 + 文档数 + chunk 数 + 操作）
- 搜索框：跨层语义检索

### 5.2 知识库详情

- 文档列表：文件名 / 类型 / 大小 / chunk 数 / 状态 / 操作
- 上传按钮（按权限显示）
- 删除按钮（按权限显示）

## 6. 验收标准

| # | 验证项 | 预期结果 |
|---|--------|----------|
| 1 | 公司级 KB | 全员可见 |
| 2 | 部门级 KB | 仅本部门可见 |
| 3 | 员工级 KB | 仅本人可见 |
| 4 | 上传文档 | 文档出现在列表中，status=indexed |
| 5 | 跨层检索 | 返回匹配结果，标注来源层级 |

## 7. 依赖

- 现有 plugins/ddw_knowledge_hierarchy/ 扩展
- RAG 向量检索（现有 core/knowledge.py）
