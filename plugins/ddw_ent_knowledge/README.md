# DDW 企业知识库引擎 (ddw_ent_knowledge)

Flat KB MVP：上传文档→解析→分块→embedding→向量存储→检索→LLM 问答（SSE 流式）。

## API 列表

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/plugins/ddw-ent-knowledge/documents/upload` | 上传文档（multipart，md/txt/json/yaml/pdf） |
| GET | `/api/v1/plugins/ddw-ent-knowledge/documents` | 文档列表（分页：page, page_size） |
| DELETE | `/api/v1/plugins/ddw-ent-knowledge/documents/{id}` | 删除文档及关联 chunks |
| POST | `/api/v1/plugins/ddw-ent-knowledge/search` | 语义检索（body: {query, top_k}） |
| POST | `/api/v1/plugins/ddw-ent-knowledge/chat` | 问答（SSE 流式，body: {query, top_k}） |
| GET | `/api/v1/plugins/ddw-ent-knowledge/health` | 健康检查 |

## 演示页

访问 `/plugins/ddw_ent_knowledge/templates/kb_demo.html`：

1. 左侧拖拽/选择文件上传文档
2. 右侧输入问题，SSE 流式回答 + 检索耗时显示

## Embedding 配置

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `DDW_EMBEDDING_API_KEY` | API Key（未设置时降级 SimpleEmbedding） | - |
| `DDW_EMBEDDING_BASE_URL` | OpenAI 兼容接口地址 | `https://api.openai.com` |
| `DDW_EMBEDDING_MODEL` | 模型名 | `text-embedding-3-small` |
| `DDW_EMBEDDING_DIM` | 向量维度 | `1536` |

## 运行测试

```bash
pytest plugins/ddw_ent_knowledge/tests/ -v
```
