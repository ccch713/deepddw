# DDW SaaS Billing Plugin v0.1.0

通用 SaaS 计费插件（不绑定培训业务，可被其他产品复用）。SaaS 场景（B/D）专用。

## 能力

- 订阅管理（个人版 / 团队版 / 企业版）
- 用量计量（事件 + Token）
- 配额检查（防止超额）
- 支付对接（微信支付 v3 + 支付宝）

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/subscriptions` | 订阅列表/创建 |
| POST | `/subscriptions/{id}/cancel` | 取消订阅 |
| POST | `/usage` | 记录用量 |
| GET | `/usage/{tenant_id}` | 查询用量 |
| GET | `/quota/{tenant_id}` | 检查配额 |
| POST | `/webhook/wechat` | 微信支付回调 |

## 事件订阅

- `training.session.completed` → 计量 `tokens_used`
- `training.assessment.completed` → 计量 `tokens_used`

## 数据模型

- `ddw_subscriptions`（租户订阅 + 限额 + 已用）
- `ddw_usage_logs`（每次用量流水）

## 支付

- 微信支付 v3（桩实现，真实需商户号 + API v3 证书）
- 支付宝（桩实现）

## 测试

```bash
pytest plugins/ddw_saas_billing/tests/ -v
# 7/7 passed
```
