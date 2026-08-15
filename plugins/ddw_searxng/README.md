# DDW SearXNG 聚合搜索插件

将 SearXNG（MIT 开源元搜索）JSON API 封装为 DDW 标准插件。

## 功能

- **聚合搜索**：`GET /api/v1/plugins/ddw-searxng/search?q=关键词&limit=5`
- **健康检查**：`GET /api/v1/plugins/ddw-searxng/health`

## 配置

| 环境变量 | 默认值 | 说明 |
|:--|:--|:--|
| `SEARXNG_URL` | `http://127.0.0.1:8888` | SearXNG 服务地址 |

## API 示例

```bash
# 搜索
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8500/api/v1/plugins/ddw-searxng/search?q=人工智能&limit=5"

# 健康检查
curl -H "Authorization: Bearer <token>" \
  "http://localhost:8500/api/v1/plugins/ddw-searxng/health"
```

## 鉴权

所有端点要求 `Authorization: Bearer <jwt>`（DDW 用户角色即可）。

## 错误处理

SearXNG 不可达时，search 端点返回：
```json
{"success": false, "error": "SEARXNG_UNREACHABLE", "detail": "..."}
```

health 端点始终返回 200，通过 `ok` 字段标识状态。
