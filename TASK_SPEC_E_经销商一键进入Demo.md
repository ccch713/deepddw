# TASK_SPEC · E · 经销商一键进入客户 Demo + 付费客户列表

> 来源：用户需求（2026-08-10 会话 dbaadaeef474）：「经销商能否直接通过自己经销商管理页面，直接进入所管理的客户的demo页面。以及已经付费客户的列表。但是不能直接进入客户的正式SaaS生产环境。」
> 状态：**待开发**（等测试反馈后排期，建议夜间 MiMo 八折窗口）
> 作者：Hermes（架构）· 执行：MiMo Code / MiniMax Code · 质量：AHE Loop

## 一、需求背景与验收

经销商（租户 14 江昆鹏等）登录后进入经销商工作台，当前已有 `/partner-demo-accounts.html`（demo 账号清单 CRUD），但：
1. 只能**看**账号清单，不能**一键进入**客户 demo（需手动复制账号密码重新登录，体验差）
2. 没有**已付费客户列表**（经销商需要知道自己名下哪些客户已付费、状态如何）

**验收标准**：
- A. 经销商工作台 demo 账号清单每行有「进入演示」按钮 → 点击后**免密自动登录**进入对应客户 demo 租户，且只能进入 demo 环境
- B. 经销商工作台有「付费客户」列表页：客户名、档位、到期时间、状态（试用中/已付费/已到期）、联系方式
- C. 安全：经销商**无法**通过任何方式进入客户正式 SaaS 生产环境（demo 登录 token 只对 demo 租户有效；生产租户在数据模型层面隔离）
- D. pytest 新增 ≥8 条测试，全量回归通过；ECS 部署后浏览器实测

## 二、目录结构与改动清单

```
plugins/ddw_partner_directory/
  router.py        # + 2 端点：POST /enter-demo、GET /paid-customers（prefix 已有: /api/v1/plugins/ddw-partner-directory）
  schemas.py       # + EnterDemoResp / PaidCustomer 模型
frontend/
  partner-demo-accounts.html   # demo 账号行加「进入演示」按钮（已有页面，只加按钮+JS）
  partner-paid-customers.html  # 新建：付费客户列表页（复用 admin.html 布局/频道样式）
  admin.html                   # 经销商侧边栏加「付费客户」入口（如适用）
core/api/auth.py   # + POST /api/v1/auth/demo-login（一次性 demo token 兑换正式会话）
```

**已确认的表结构（2026-08-10 实测 ECS）**：
- `partner_demo_accounts`：id / client_tenant_id / client_name / client_industry / demo_url / demo_phone / demo_password / demo_note / status('active') / expires_at / **tenant_id(归属经销商租户=14)** / created_at / updated_at
  - **没有 owner_partner_id / is_demo 字段**——归属靠 `tenant_id`，表内记录全是 demo 环境账号（安全靠 client_tenant_id 指向 demo 租户）
- `tenants`：id / name / **plan**(free|enterprise) / status / contact_phone / created_at / updated_at
  - 嘉必优租户 13 = enterprise/active/18571998165；经销商租户 14 = enterprise

**禁止改动**：core/auth/ 既有认证流程、正式登录端点逻辑、租户隔离中间件（只读复用）、partner_demo_accounts 表结构（无新字段，用现有字段）。

## 三、核心设计

### 3.1 一键进入 Demo（免密登录）

**流程**：
1. 经销商（如江昆鹏，tenant_id=14）在 `partner-demo-accounts.html` 点「进入演示」
2. 前端调 `POST /api/v1/plugins/ddw-partner-directory/enter-demo {account_id}`（经销商自己的 JWT 鉴权）
3. 后端校验：`account.tenant_id == claims.tenant_id`（归属校验，防止经销商 A 进入经销商 B 的客户）且 `account.status == 'active'` → 用该 demo 账号（demo_phone/demo_password）签发**短时 demo token**（expires 15 分钟，`scope=demo_enter`，payload 含 demo 账号 user_id + client_tenant_id + role）
   - **注意**：demo 账号是已存在的真实用户（如 18571998165 万永刚），后端直接查 users 表按 demo_phone 找 user_id；查不到则返回 404
4. 前端带 token 跳转 `/?demo_token=xxx` → `auth.js` 检测到参数 → 调 `POST /api/v1/auth/demo-login {token}` 兑换正式会话 JWT → 进入客户 demo 后台（client_tenant_id 租户）

**安全设计**：
- `enter-demo` 用经销商自己的 JWT 鉴权（必须校验 account.tenant_id 归属）
- demo token 短时（15 分钟）+ **单次兑换**（兑换后立即失效，Redis/内存存已用 token 黑名单）+ scope 限定
- demo-login 兑换出的正式 JWT 的 tenant = client_tenant_id（客户 demo 租户），role 沿用 demo 账号 role
- **生产环境隔离**：partner_demo_accounts 只录 demo 租户账号（数据录入规范），正式生产租户不在表中；demo token 只能兑换 client_tenant_id 对应租户

### 3.2 付费客户列表（方案 B：聚合派生，零新表）

**数据源**：`partner_demo_accounts`（归属经销商 tenant_id）+ `tenants`（plan/status/contact_phone）聚合派生，不建新表。

**端点**：`GET /api/v1/plugins/ddw-partner-directory/paid-customers` → **裸数组**（铁律：列表端点返回裸数组，禁 items 信封）：
```json
[
  {
    "client_tenant_id": 13,
    "client_name": "嘉必优生物技术(武汉)股份有限公司",
    "plan": "enterprise",
    "status": "active",
    "contact_phone": "18571998165",
    "expires_at": null
  }
]
```
- 逻辑：查当前经销商 tenant_id 名下所有 partner_demo_accounts → 按 client_tenant_id 去重 → join tenants 取 plan/status/contact_phone → 每条记录带 expires_at（partner_demo_accounts.expires_at）
- 付费判定：`plan != 'free'` → 已付费（enterprise）；`plan == 'free'` → 试用中

## 四、测试用例（≥8 条）

| # | 用例 | 断言 |
|---|------|------|
| 1 | 经销商调 enter-demo 且 account 归属自己 | 200 + 返回 demo_token（含 demo user_id/tenant_id） |
| 2 | 经销商调 enter-demo 但 account 归属别人 | 403 |
| 3 | 非经销商（普通用户）调 enter-demo | 403 |
| 4 | account 不存在 | 404 |
| 5 | account.status != 'active'（inactive）| 403 |
| 6 | demo-login 兑换合法 token | 200 + 正式会话 JWT，进入 client_tenant_id 租户 |
| 7 | demo-login 重复兑换同一 token | 401（单次兑换） |
| 8 | paid-customers 返回裸数组 + 字段完整 | Array.isArray + 每项含 client_name/plan/status/contact_phone |
| 9 | paid-customers 只返回当前经销商名下客户 | 无他人数据 |

## 五、开发顺序与禁止事项

1. 后端：router.py + 2 端点（enter-demo / paid-customers，归属校验 tenant_id）→ schemas → auth.py demo-login（短时 token + 单次兑换黑名单）→ 测试
2. 前端：partner-demo-accounts.html 加「进入演示」按钮 → auth.js demo_token 处理 → partner-paid-customers.html 新建 + 侧边栏入口
3. AHE Loop：每模块 ruff + pytest → 全量回归 → 部署 ECS → curl 验证 → 浏览器实测
4. 注意：`enter-demo` 校验用 `account.tenant_id == claims["tenant_id"]`；demo-login 兑换后正式 JWT tenant=client_tenant_id

**禁止**：改正式登录端点行为、改租户隔离逻辑、跳过归属校验、新依赖（Pillow/redis 已有）、改 partner_demo_accounts 表结构。
