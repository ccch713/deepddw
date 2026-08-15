# ddw_ai_readiness 插件

企业 AI 就绪度自评插件，用于接收问卷答案、服务端评分、商机分级（A/B/C）、SQLite 入库、销售端查询/统计。

## 功能

- 接收前端问卷答案（匿名可提交）
- 服务端评分（防篡改）
- 商机分级（A/B/C 级）
- SQLite 自动建库，零配置
- 销售端查询与统计

## API 端点

| 方法 | 路径 | 说明 | 鉴权 |
|------|------|------|------|
| POST | `/api/v1/plugins/ddw_ai_readiness/submissions` | 提交测评 | 匿名 |
| GET | `/api/v1/plugins/ddw_ai_readiness/submissions` | 销售端列表 | 需登录 |
| GET | `/api/v1/plugins/ddw_ai_readiness/submissions/{sid}` | 销售端详情 | 需登录 |
| GET | `/api/v1/plugins/ddw_ai_readiness/stats` | 统计数据 | 匿名 |
| GET | `/api/v1/plugins/ddw_ai_readiness/health` | 健康检查 | 匿名 |

## 部署

SQLite 自动建库，零配置。数据库文件位于 `plugins/ddw_ai_readiness/data/readiness.db`。

## 前端入口

前端 HTML 文件位于 `商务物料/DDW-就绪度自评/ddw-ai-readiness.html`，需配置 `API_BASE` 指向后端地址。

## 生产部署建议

建议由 Caddy/网关层对销售端接口（列表/详情）添加访问控制。