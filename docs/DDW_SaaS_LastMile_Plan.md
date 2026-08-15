# DDW SaaS 最后一公里 — 开发规划
> 日期：2026-08-02
> 优先级：P0（有客户要签单，今晚开始）

---

## 目标

让客户能自助完成：注册 → 选套餐 → 支付 → 立即使用 DDW 平台。

## 现状（已验证 + 风险标注）

| 能力 | 状态 | 代码位置 | 风险 |
|:---|:---|:---|:---|
| 多租户中间件 | ✅ 骨架就位 | `core/middleware/tenant.py` | ⚠️ 只提取 tenant_id 到 request.state，ORM 查询未自动过滤 |
| TenantMixin | ✅ 20+ 表继承 | `core/database/models.py` | ⚠️ Mixin 定义了字段，但 SQLAlchemy event 自动注入未实现 |
| JWT 认证 | ✅ 完整 | `core/auth/jwt.py` | — |
| 用户模型 | ✅ 完整 | `core/database/models.py:User` | — |
| Token 额度 | ✅ 完整 | `plugins/ddw-token-manager/` | — |
| 审计日志 | ✅ 完整 | `core/database/models.py:AuditLog` | — |
| ECS 生产 | ✅ 运行中 | `ddw.9cio.com` | ⚠️ 当前是单实例单租户，非多租户共享 |
| 自动 ORM 租户过滤 | ❌ 未实现 | — | **必须先做，否则多租户数据泄漏** |
| 用户自助注册 | ❌ 未实现 | — | SaaS 入口 |
| 在线支付 | ❌ 未实现 | — | 商业化 |

## 开发任务（按顺序执行）

### Phase 0: 自动租户隔离层（前置必须，0.5 天）

**Task 0.1: SQLAlchemy ORM 自动租户过滤**
- 监听 `before_flush` 事件，自动为新对象注入 `tenant_id`
- 监听 `do_orm_execute` 事件，自动为所有 SELECT 语句注入 `WHERE tenant_id = ?`
- 参考 PRD v5.3 描述的 SQLAlchemy event 方案
- 文件：`core/database/tenant_filter.py`（新建）
- 测试：验证跨租户数据完全隔离

**Task 0.2: 租户创建流程**
- 注册时自动创建 Tenant 记录
- 默认配额：免费版 5 用户 / 标准版 50 用户 / 企业版 200 用户
- 文件：`core/api/auth.py` 扩展

### Phase 1: 注册 + 套餐（今晚）

**Task 1.1: 注册 API**
- 路径：`POST /api/v1/auth/register`
- 字段：手机号 + 验证码 + 企业名（可选）
- 验证码发送：复用现有 SMS auth（`core/auth/sms_auth.py`）
- 注册后自动创建 Tenant + User + 默认 TokenQuota
- 文件：`core/api/auth.py` 新增 register 端点

**Task 1.2: 注册页面**
- 单页 HTML（和 DDW Demo v5 风格一致）
- 字段：手机号 → 验证码 → 企业名 → 提交
- 去 AI 化（claude-design + qu-ai-wei 规范）
- 文件：`frontend/saas-register.html`

**Task 1.3: 套餐选择页面**
- 三个套餐：
  - 免费版：5 用户，基础 LLM，社区支持
  - 标准版：¥4,999 一次性，50 用户，商业插件，邮件支持
  - 企业版：¥19,999 一次性，200 用户，FDE 现场，7×12 工单
- 注册后立即展示，免费版自动激活
- 文件：`frontend/saas-pricing.html`

### Phase 2: 支付集成（明天）

**Task 2.1: 微信支付集成**
- JSAPI 支付（微信内打开）+ Native 支付（扫码）
- 对接 ddw-token-manager 的 SubscriptionInfo 模型
- 支付成功后自动升级套餐、调整 TokenQuota
- 文件：`core/api/payment.py`（新建）

**Task 2.2: 支付结果页 + 套餐管理**
- 支付成功/失败回调页面
- 套餐升级/续费入口
- 文件：`frontend/saas-billing.html`

### Phase 3: 管理后台（后天）

**Task 3.1: 租户管理后台**
- 用量概览（Token 消耗、API 调用次数、插件使用情况）
- 用户管理（邀请/移除成员）
- API Key 管理
- 文件：`frontend/saas-admin.html`

**Task 3.2: 对接 ddw-token-manager**
- 实时额度查询 API
- 额度预警（余额不足时通知）
- 文件：`plugins/ddw-token-manager/router.py` 扩展

## 技术约束

1. 前端用纯 HTML + CSS + JS（和 Demo v5 一致，不引入框架）
2. API 遵循 `/api/v1/` 前缀
3. 所有新表必须继承 `TenantMixin`
4. 去 AI 化（claude-design + qu-ai-wei）
5. 注册/支付页面必须移动端友好（微信内打开）

## 验收标准

| 项 | 标准 |
|:---|:---|
| 注册 | 手机号 + 验证码 → 自动创建租户 → 进入平台 |
| 套餐 | 3 个套餐清晰展示 → 免费版一键激活 → 付费版跳支付 |
| 支付 | 微信内 JSAPI 支付 → 成功后自动升级 |
| 管理 | 用量概览 + 用户管理 + API Key |
| 移动端 | 微信内打开正常显示、注册流程完整 |

## 开发顺序

```
今晚 (Phase 1):
  Task 1.1 注册 API → Task 1.2 注册页面 → Task 1.3 套餐页面
  
明天 (Phase 2):
  Task 2.1 微信支付 → Task 2.2 支付页面
  
后天 (Phase 3):
  Task 3.1 管理后台 → Task 3.2 额度对接
```

## 账号体系补充说明

微信支付需要微信商户号（需营业执照）。如果还没有：
- 备选方案 A：先做免费版注册（零支付门槛），客户注册即用
- 备选方案 B：对公转账 + 人工激活（管理后台手动操作）
- 备选方案 C：接入支付宝当面付（门槛更低）
