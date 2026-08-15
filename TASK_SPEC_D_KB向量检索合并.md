# TASK_SPEC：kb/search 真向量检索集成 + 知识库双套合并（D 项）

> 优先级：P1（用户明确要求执行）
> 执行者：MiMo Code CLI（mimo run headless）
> 验收者：Hermes（DeepSeek 新标准 6 维验收）
> 关联：P2-1 遗留（kb/search 未集成向量检索 + 双套并存）

---

## 一、背景

P2-1 完成知识库三层权限后遗留 2 个问题：
1. **POST /kb/search 未做真向量检索**：当前只按 ACL 过滤返回 KBDocument 元数据列表，没有调用现有 services/hierarchical_retriever.py 的三阶段检索
2. **知识库双套并存**：core/api/knowledge.py（/knowledge/bases 旧版，基于类别）与插件 kb_router.py（/plugins/ddw-knowledge-hierarchy/kb/* 新版，三层权限）两套共存

## 二、目标

1. **kb/search 集成真向量检索**：搜索时先 ACL 过滤出可见 KB → 取 KB 下文档 → 调 HierarchicalRetriever.search 做真实向量检索（flat 模式起步，hybrid 可选）→ 返回带相关性分块的结果
2. **双套合并**：统一入口为插件 kb_router（三层权限版），core/api/knowledge.py 的旧端点保留但标注 deprecated，前端/调用方切换到插件路径

## 三、目录结构（只改这些）

```
plugins/ddw_knowledge_hierarchy/
├── kb_router.py          # 修改：/kb/search 集成向量检索
├── services/
│   └── kb_vector.py      # 新增：KBDocument → Document 映射 + 向量检索封装
└── tests/
    └── test_kb_search_vector.py   # 新增：5 条测试
core/api/
└── knowledge.py          # 修改：端点标注 deprecated（不改逻辑）
```

## 四、核心逻辑

### 4.1 kb_vector.py（新增）

```python
"""KBDocument → 向量检索桥接。"""

async def search_kb_documents(
    db: AsyncSession,
    query: str,
    kb_ids: List[int],
    tenant_id: int,
    search_mode: str = "flat",
    max_chunks: int = 10,
) -> List[Dict]:
    """1. 查 KBDocument 列表（按 kb_ids）
       2. 通过 Document.filename/原文档关联，收集 document_id 集合
       3. 实例化 HierarchicalRetriever(db, vector_store)
       4. retriever.search(query, tenant_id=tenant_id, document_ids=doc_ids, search_mode=search_mode)
       5. 返回 retrieval_chunks 转 dict（含 text/chunk_index/document_id/score）
    """
```

注意：若 Document 与 KBDocument 无直接外键，通过文件名（filename）匹配，或 KBDocument 增加 document_id 列（如缺则 ALTER 补列 + 上传时回填）。**优先加列回填**（上传 KBDocument 时同步建 Document + vector index，若已有 Document 则关联 id）。

### 4.2 kb_router.py /kb/search 改造

```python
@router.post("/kb/search")
async def search_kbs(req: KBSearchRequest, principal=Depends(get_principal)):
    # 1. ACL 过滤可见 KB（现有逻辑保留）
    # 2. 调 kb_vector.search_kb_documents(...) 做真向量检索
    # 3. 返回 {"query", "results": [{kb_id, doc_id, filename, score, text_head}], "total"}
    # 4. 若向量库无数据 → 降级返回现有元数据列表（不报错）
```

### 4.3 core/api/knowledge.py deprecated 标注

- 每个端点 docstring 加 `@deprecated 请使用 /api/v1/plugins/ddw-knowledge-hierarchy/kb/*`
- 逻辑不动（避免破坏现有调用）

## 五、测试用例（5 条）

| # | 用例 | 断言 |
|---|------|------|
| 1 | 有向量数据时 search 返回分块结果 | results 含 score/text_head |
| 2 | 无向量数据时降级返回元数据 | 不 500，返回元数据列表 |
| 3 | ACL 过滤仍生效 | member 看不到公司外 KB 的检索结果 |
| 4 | kb_vector 映射正确 | KBDocument → Document id 关联成功 |
| 5 | deprecated 标注存在 | knowledge.py 含 "@deprecated" |

## 六、验收标准

| # | 维度 | 标准 |
|---|------|------|
| A | pytest | 新增 5 条全过，全量回归 150+ 无破坏 |
| B | ruff | 零新增 error |
| C | 铁律2 | /kb/search 返回 {results, total} |
| D | 功能 | 真向量检索生效（有分块结果）或优雅降级 |
| E | 兼容 | 旧 /knowledge/bases 不破坏 |

## 七、红线

1. 不删 core/api/knowledge.py（只标注 deprecated）
2. 不改 hierarchical_retriever.py 现有逻辑
3. commit：`feat(kb): search集成真向量检索+双套deprecated标注 [LLM: mimo-code]`，不 push
4. 不要动 ECS 上的文件
