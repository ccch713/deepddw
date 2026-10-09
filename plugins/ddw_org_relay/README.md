# ddw-org-relay · 组织连接插件（bindcode-v1 服务端）

让本 deepDDW 实例作为**组织后端**被 DDW AI 助手系列 App 绑定连接（开放协议
[bindcode-v1](../../docs/组织连接协议-bindcode-v1.md)）。**默认关闭**，配置开启。

```text
员工 App ──绑定码──▶ ┌───────────── 本 deepDDW 实例 ─────────────┐
                    │ pub 三件（产品令牌+限速）：bind/unbind/me   │
                    │ 成员 access_token → chat/completions        │──▶ llm_gateway
                    │ admin/*（实例静态 Token，不暴露公网）        │    （部署者自配供应商）
                    └────────────────────────────────────────────┘
```

## 开启

`config/deployment.yaml`：

```yaml
org_relay:
  enabled: true
  product_tokens:            # 产品令牌（可多枚；App 产品侧持有，公网端点鉴权）
    - "a-very-long-random-product-token"
  server_base_url: ""        # 本实例 LLM 端点 base；公网部署务必显式配置
                             # （例：https://ddw.example.com/api/v1/plugins/ddw-org-relay）
  rate_limit_per_token: 10   # 每产品令牌 10 req/min（协议 §6 绑定端点限速）
  bindcode_ttl_min: 15       # 绑定码默认时效（分钟）
  bindcode_max_uses: 50      # 绑定码默认用次
```

或环境变量：`DDW_ORG_RELAY_ENABLED=1`、`DDW_ORG_RELAY_PRODUCT_TOKENS=tok1,tok2`、
`DDW_ORG_RELAY_SERVER_BASE_URL=...` 等（环境变量优先）。

## 使用流程

1. **管理员签码**（实例静态 Token，即 `DDW_ACCESS_TOKEN`）：

   ```bash
   # 建组织（org_secret 仅此一次返回，丢失可 rotate）
   curl -X POST :8500/api/v1/plugins/ddw-org-relay/admin/orgs \
        -H "Authorization: Bearer $DDW_ACCESS_TOKEN" \
        -H 'Content-Type: application/json' -d '{"name":"某某诊所","plan":"light"}'
   # 签发绑定码（默认 15 分钟 / 50 人次）
   curl -X POST :8500/api/v1/plugins/ddw-org-relay/admin/orgs/<org_id>/bindcode \
        -H "Authorization: Bearer $DDW_ACCESS_TOKEN" \
        -H 'Content-Type: application/json' -d '{"ttl_min":15,"max_uses":50}'
   ```

2. **员工 App 粘贴/扫码绑定**（App 产品侧调公网三件，Bearer 产品令牌）：

   - `POST /api/v1/relay/org/pub/bind` `{user_id, code}` → `{bound, org}`
   - `POST /api/v1/relay/org/pub/unbind` `{user_id}` → `{bound: false}`
   - `GET  /api/v1/relay/org/pub/me?user_id=...` → `{bound, org, org_consumed_total}`

   `org` 对象含协议 §3.1 可选字段：`server_base_url`（本实例 LLM 端点）、
   `access_token`（成员级凭证，解绑/吊销即失效）、`models`（部署者配置的模型）。

3. **成员直连本实例 LLM 端点**（OpenAI 兼容）：

   ```bash
   curl -X POST <server_base_url>/chat/completions \
        -H "Authorization: Bearer <org.access_token>" \
        -H 'Content-Type: application/json' \
        -d '{"messages":[{"role":"user","content":"hi"}]}'
   ```

## 两条产品边界（实现层面）

- **LLM 供给完全由部署者自配**：`chat/completions` 背后是本实例 `llm_gateway`
  的供应商配置（DeepSeek/Ollama/任意自建网关，见 `/api/v1/llm/config`）。
  本插件不内置、不预设任何外部模型渠道。
- **绑定不是后端锁定**：`unbind` 仅结束绑定关系并使成员令牌失效；App 侧个人
  数据/个人模式不受影响（协议 §4）。服务端不持有员工个人数据，解绑不删任何
  用量流水（元数据）。

## 安全要点（协议 §6）

| 项 | 实现 |
| --- | --- |
| org_secret | ≥32 字节随机，Fernet 加密落盘；支持轮换（旧码时效内仍有效）；永不出现在任何响应 |
| 校验 | HMAC-SHA256 前 16 hex，`hmac.compare_digest` 常数时间比较 |
| 公网限速 | 每产品令牌 10 req/min（滑动窗口，429 + Retry-After） |
| 管理端 | 复用实例静态 Token 门禁；**不应暴露公网**（防火墙/反代只放行 `/api/v1/relay/org/pub/*` 与 `chat/completions`） |
| 日志/流水 | 仅元数据（org_id/user_id/动作/模型/token 数），不落对话正文 |
| 存储 | 独立库 `data/org_relay.db`；不建用户账号/角色体系，只记录绑定关系 |

## 端点一览

| 端点 | 鉴权 | 说明 |
| --- | --- | --- |
| `POST /api/v1/relay/org/pub/bind` | 产品令牌 | 绑定（403 伪造 / 410 过期 / 409 超用次或已绑他组织 / 404 已吊销） |
| `POST /api/v1/relay/org/pub/unbind` | 产品令牌 | 解绑（幂等） |
| `GET /api/v1/relay/org/pub/me` | 产品令牌 | 组织状态查询 |
| `POST /api/v1/plugins/ddw-org-relay/chat/completions` | 成员 access_token | OpenAI 兼容对话（支持 stream）；组织配额可配 |
| `.../admin/orgs`（GET/POST）及子资源 | 实例 Token | 建组织/详情/签码/吊销/轮换/停用/配额/解绑/用量 |
| `GET .../health` | 无 | `{"protocol":"bindcode","protocol_version":"1"}`（协议 §7） |

测试：`pytest plugins/ddw_org_relay/tests/ -q`（47 例：签发/校验单测 + 全链路矩阵）。
