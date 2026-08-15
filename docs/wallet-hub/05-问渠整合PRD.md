# 问渠 × Wallet Hub 整合 PRD

> 版本：v1.0 | 日期：2026-08-13 | 状态：已实现

## 一、产品定位

问渠学科包（ddw_wenqu_tutor）作为 DDW 支付中台（ddw_wallet v0.2.0）的业务消费方，通过 HTTP API 实现学习会话的余额校验与自动扣费。

## 二、用户故事

| 角色 | 场景 | 预期 |
|---|---|---|
| 学生 | 点击"开课"按钮 | 系统检查钱包余额 ≥ ¥1，余额不足弹出充值引导（402） |
| 学生 | 完成一节课后点"下课" | 系统按活跃分钟 × ¥0.2 自动扣费，返回扣费金额和剩余余额 |
| 家长 | 查看孩子学习统计 | 统计页面展示累计消费金额（从 wallet 流水聚合） |

## 三、功能清单

| ID | 功能 | 优先级 | 状态 |
|---|---|---|---|
| F1 | 开课前余额校验（三钱包总额 ≥ 100 分） | P0 | ✅ 已实现 |
| F2 | 下课自动扣费（活跃分钟 × 1200 分/分钟，幂等） | P0 | ✅ 已实现 |
| F3 | 余额不足返回 402 + INSUFFICIENT_BALANCE | P0 | ✅ 已实现 |
| F4 | 钱包服务不可用降级（开课放行 + warning 日志） | P0 | ✅ 已实现 |
| F5 | 混合扣费（recharge → income → skin 顺序） | P0 | ✅ 已实现 |
| F6 | 前端充值引导弹窗（402 时触发） | P1 | 🔲 待开发 |
| F7 | 家长端消费明细（从 wallet transactions 聚合） | P1 | 🔲 待开发 |

## 四、API 契约（问渠 → wallet hub）

### 4.1 查余额
```
GET /api/v1/plugins/ddw_wallet/accounts/{user_id}/balances
→ 200 {"recharge_balance_cents": 5000, "income_balance_cents": 1000, "skin_balance_cents": 0}
```

### 4.2 扣费（混合钱包）
```
POST /api/v1/plugins/ddw_wallet/charges/fallback
{
  "user_id": "student_name",
  "charge_type": "study_time",
  "subject": "physics",
  "ref_id": "WS1723456789000abcdef1234",  // session_id，幂等键
  "ref_type": "session",
  "amount_cents": 2400,
  "balance_priority": "recharge,income,skin"
}
→ 200 {"txn_no": "C20260813ABCD1234", "amount_cents": 2400, "balance_after_cents": 2600}
→ 402 {"code": "INSUFFICIENT_BALANCE", "balance_cents": 50}
```

## 五、错误处理

| 场景 | HTTP 状态码 | 错误码 | 问渠行为 |
|---|---|---|---|
| 余额不足 | 402 | INSUFFICIENT_BALANCE | 前端弹充值引导 |
| 钱包服务超时/不可用 | 503 | WALLET_SERVICE_ERROR | 开课：放行 + warning；下课：记录 charge_error 事件 |
| 重复扣费（幂等命中） | 200 | — | 返回首次扣费结果，不重复扣 |
| 会话不存在 | 404 | — | 返回"Session not found" |
| 会话已结束 | 400 | — | 返回"already ended/billed" |

## 六、非功能需求

| 项 | 要求 |
|---|---|
| 超时 | wallet API 调用 10 秒超时 |
| 连接池 | httpx.AsyncClient 进程级单例，复用 TCP 连接 |
| 幂等 | ref_id = session_id，同一节课只扣一次 |
| 降级 | wallet 不可用时开课放行（不影响学习体验） |
| 金额单位 | 全部整数分（cent），避免浮点精度问题 |
