# DDW AI Hub — SaaS 最后一公里 + 前端规范 全量开发提示词
# 发送给 16G Mac mini 上的 MiniMax Code
# 预计执行时间：4-6 小时（含自检循环）

---

## 任务概述

你是一个企业级 Python 全栈开发者。今晚的任务是为 DDW AI Hub 底座平台完成 **SaaS 最后一公里** 的全部代码开发，包括：自动租户隔离层、用户自助注册、套餐选择页面、管理后台页面。所有代码必须通过自检后才能进入下一步。

## 第零步：读取项目上下文（必做，不要跳过）

在写任何代码之前，你必须完整读取以下文件：

```
# 核心 PRD
/Users/chenye/workspace/ddw-ai-hub/PRD/DDW_AI_Hub_v5.4_MASTER.md

# 架构决策记录（今晚最新）
/Users/chenye/workspace/ddw-ai-hub/docs/DDW_Architecture_Decision_Records.md

# SaaS 开发规划（今晚最新）
/Users/chenye/workspace/ddw-ai-hub/docs/DDW_SaaS_LastMile_Plan.md

# 前端设计规范
/Users/chenye/workspace/ddw-ai-hub/docs/DDW_Frontend_Design_Standard.md

# 前端架构策划
/Users/chenye/workspace/ddw-ai-hub/docs/DDW_Frontend_UI_Architecture_Plan.md

# 现有代码（重点读，理解已有模式）
/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/core/main.py
/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/core/middleware/tenant.py
/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/core/database/models.py
/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/core/auth/jwt.py
/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/core/config.py
/Users/chenye/workspace/ddw-ai-hub/plugins/ddw-token-manager/models.py
/Users/chenye/workspace/ddw-ai-hub/plugins/ddw-token-manager/router.py

# 前端 Demo v5（视觉参考）
/Users/chenye/workspace/ddw-ai-hub/frontend/DDW_Platform_Demo_v5.html

# 插件开发规范
/Users/chenye/workspace/ddw-ai-hub/docs/DDW_Plugin_Development_Guide.md
```

**读完后用一句话总结你对项目架构的理解，然后才开始编码。**

---

## 技术栈（必须遵守）

- Python >= 3.11, < 3.14
- FastAPI >= 0.110.0 + Uvicorn
- SQLAlchemy >= 2.0.30（Async）
- PyJWT >= 2.8.0（RSA256）
- Jinja2 >= 3.1（模板渲染）
- pytest >= 8.0 + httpx AsyncClient
- 禁止使用 LangChain / LlamaIndex / CrewAI
- 前端：纯 HTML + CSS + JS（不引入 React/Vue/Angular）

---

## Phase 0：自动 ORM 租户隔离层（最高优先级，必须先做）

### Task 0.1：SQLAlchemy ORM 自动租户过滤

创建文件：`cloud-llm/ddw-ai-hub/core/database/tenant_filter.py`

要求：
1. 监听 SQLAlchemy `before_flush` 事件，自动为所有继承了 `TenantMixin` 的新对象注入 `tenant_id`
2. 监听 `do_orm_execute` 事件，自动为所有 SELECT 语句注入 `WHERE tenant_id = :tenant_id` 条件
3. `tenant_id` 从 FastAPI 的 `request.state.tenant_id` 获取（已有 tenant_middleware 设置）
4. 使用 contextvars 在请求上下文中传递 tenant_id，避免在 ORM 层依赖 FastAPI Request 对象
5. 提供 `set_tenant_context(tenant_id)` 和 `get_tenant_context()` 上下文管理器
6. 在 `core/main.py` 的 lifespan 中注册 SQLAlchemy event listeners
7. 为未设置 tenant_id 的请求（如 admin 操作）提供 `bypass_tenant_filter()` 跳过机制

### Task 0.2：租户模型完善

检查 `core/database/models.py` 中的 `Tenant` 模型，确保包含以下字段：
- `id`（主键）
- `name`（企业/组织名称）
- `plan`（套餐类型：free/standard/enterprise）
- `max_users`（最大用户数）
- `status`（active/suspended/cancelled）
- `created_at` / `updated_at`
- `settings`（JSON 字段，存储租户自定义配置）

如果缺失，补充完整。

### Task 0.3：租户创建服务

创建文件：`cloud-llm/ddw-ai-hub/core/services/tenant_service.py`

提供以下方法：
- `create_tenant(name, plan='free')` → 创建租户 + 默认配额
- `get_tenant_by_id(tenant_id)` → 查询租户
- `upgrade_plan(tenant_id, new_plan)` → 升级套餐
- `get_tenant_usage(tenant_id)` → 获取用量统计

### 自检循环（Phase 0 完成后必须执行）

```bash
cd /Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub
python -c "from core.database.tenant_filter import set_tenant_context, get_tenant_context; print('Import OK')"
python -m pytest tests/ -v --tb=short -k "tenant" 2>&1 | tail -20
# 如果没有 tenant 相关测试，创建 tests/test_tenant_filter.py 并运行
```

**只有全部 PASS 才能进入 Phase 1。如果有 FAIL，修复后重新运行。**

---

## Phase 1：用户自助注册 API + 页面

### Task 1.1：注册 API

修改文件：`cloud-llm/ddw-ai-hub/core/api/auth.py`

新增端点：
```
POST /api/v1/auth/register
  请求体：{phone, code, enterprise_name?}
  逻辑：
    1. 验证手机验证码（复用现有 sms_auth.py）
    2. 检查手机号是否已注册
    3. 创建 Tenant（如果 enterprise_name 提供）
    4. 创建 User（关联 tenant_id）
    5. 创建默认 TokenQuota（免费版 5 用户配额）
    6. 返回 JWT token
  响应：{token, user_id, tenant_id, plan}

POST /api/v1/auth/send-code
  请求体：{phone}
  逻辑：发送短信验证码（复用 sms_auth.py）
  响应：{success, message}
```

### Task 1.2：注册页面

创建文件：`/Users/chenye/workspace/ddw-ai-hub/frontend/saas-register.html`

**设计规范（严格遵守）**：
- 锚点：Ant Design 企业 OA 风格（泛微/蓝凌）
- 主色：`#1890FF`，深色：`#001529`
- 圆角：≤2px（不要大圆角卡片）
- 字体：`-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`
- 禁止：渐变背景、box-shadow、emoji 图标、AI-slop 词汇（赋能/助力/打造/闭环/护航/全方位）
- 图标：SVG 线条图标（不使用 emoji）
- 布局：居中卡片式，最大宽度 400px
- 移动端适配：微信内打开友好

页面内容：
1. 顶部：DDW Logo + "注册 DDW AI Hub"
2. 手机号输入框
3. 验证码输入框 + "获取验证码" 按钮（60 秒倒计时）
4. 企业名称（可选）
5. "免费注册" 按钮
6. 底部：已有账号？直接登录

交互逻辑：
- 点击"获取验证码" → POST /api/v1/auth/send-code
- 点击"免费注册" → POST /api/v1/auth/register
- 成功后跳转到套餐选择页面 saas-pricing.html
- 失败显示错误提示（手机号已注册/验证码错误等）

### Task 1.3：套餐选择页面

创建文件：`/Users/chenye/workspace/ddw-ai-hub/frontend/saas-pricing.html`

页面内容：
1. 三个套餐卡片（水平排列，移动端垂直）：

**免费版**：
- 价格：¥0
- 5 个用户
- 基础 LLM 对话
- 社区支持
- 按钮："当前套餐"（已激活时灰显）

**标准版**：
- 价格：¥4,999（一次性）
- 50 个用户
- 全部商业插件
- 邮件技术支持
- 按钮："立即升级"

**企业版**：
- 价格：¥19,999（一次性）
- 200 个用户
- FDE 现场部署
- 7×12 工单支持
- 按钮："联系我们"（跳转邮件）

2. 底部：跳过，进入控制台 → saas-admin.html

### 自检循环（Phase 1 完成后必须执行）

```bash
# 测试注册 API
python -m pytest tests/test_auth.py -v --tb=short 2>&1 | tail -20

# 验证 HTML 文件
python3 -c "
import os
for f in ['frontend/saas-register.html', 'frontend/saas-pricing.html']:
    path = f'/Users/chenye/workspace/ddw-ai-hub/{f}'
    assert os.path.exists(path), f'{f} not found'
    size = os.path.getsize(path)
    assert size > 1000, f'{f} too small ({size}B)'
    with open(path) as fh:
        content = fh.read()
    assert '<!DOCTYPE html>' in content, f'{f} missing DOCTYPE'
    assert '</html>' in content, f'{f} missing closing tag'
    # 去 AI 化检查
    ai_words = ['赋能','助力','打造','闭环','护航','全方位','一站式','深度赋能']
    found = [w for w in ai_words if w in content]
    assert not found, f'{f} contains AI-slop words: {found}'
    assert 'linear-gradient' not in content, f'{f} has gradient'
    assert 'box-shadow' not in content, f'{f} has shadow'
    print(f'✅ {f}: {size}B, no AI-slop, no gradient, no shadow')
print('All HTML checks passed')
"
```

**只有全部 PASS 才能进入 Phase 2。**

---

## Phase 2：管理后台页面

### Task 2.1：租户管理后台

创建文件：`/Users/chenye/workspace/ddw-ai-hub/frontend/saas-admin.html`

这是一个单页应用（SPA），使用 hash 路由，包含以下子页面：

**子页面 1：用量概览 `#/overview`**
- 当前套餐信息（免费版/标准版/企业版）
- Token 本月消耗量 + 趋势图（纯 CSS 柱状图，不引入 Chart.js）
- API 调用次数（本月/今日/当前 QPS）
- 活跃用户数 / 总用户数
- 插件使用情况（每个插件的调用次数排行）

**子页面 2：用户管理 `#/users`**
- 用户列表表格（姓名/手机号/角色/状态/最后登录时间）
- 邀请用户按钮（输入手机号 → 发送邀请）
- 移除用户按钮
- 角色切换（admin/member/viewer）

**子页面 3：API Key 管理 `#/apikeys`**
- 已有 Key 列表（名称/创建时间/最后使用/状态）
- 创建新 Key 按钮
- 禁用/删除 Key

**子页面 4：套餐管理 `#/billing`**
- 当前套餐详情
- 升级/续费入口
- 用量预警设置（余额不足时通知）

**子页面 5：系统设置 `#/settings`**
- 企业名称修改
- 通知设置
- 安全设置

**设计规范**：
- 左侧导航栏（深色 `#001529`，和 Demo v5 一致）
- 顶部标题栏
- 主内容区
- 响应式（移动端导航折叠）

### Task 2.2：管理后台 API

修改文件：`cloud-llm/ddw-ai-hub/core/api/admin.py`

新增端点：
```
GET  /api/v1/admin/overview    → 用量概览数据
GET  /api/v1/admin/users       → 用户列表
POST /api/v1/admin/users/invite → 邀请用户
DELETE /api/v1/admin/users/{id} → 移除用户
GET  /api/v1/admin/apikeys     → API Key 列表
POST /api/v1/admin/apikeys     → 创建 API Key
DELETE /api/v1/admin/apikeys/{id} → 删除 API Key
GET  /api/v1/admin/billing     → 套餐和用量信息
```

所有端点必须：
1. 使用 `require_admin` 依赖（只有 admin 角色可访问）
2. 使用 `set_tenant_context` 设置租户上下文
3. 返回标准 JSON 格式：`{success: true, data: {...}}`

### 自检循环（Phase 2 完成后必须执行）

```bash
# 运行所有测试
python -m pytest tests/ -v --tb=short 2>&1 | tail -30

# 验证管理后台 HTML
python3 -c "
import os
f = '/Users/chenye/workspace/ddw-ai-hub/frontend/saas-admin.html'
assert os.path.exists(f), 'saas-admin.html not found'
size = os.path.getsize(f)
assert size > 5000, f'too small ({size}B)'
with open(f) as fh:
    content = fh.read()
assert '<!DOCTYPE html>' in content
assert 'overview' in content, 'missing overview page'
assert 'users' in content, 'missing users page'
assert 'apikeys' in content, 'missing apikeys page'
assert 'billing' in content, 'missing billing page'
assert 'settings' in content, 'missing settings page'
ai_words = ['赋能','助力','打造','闭环','护航','全方位','一站式']
found = [w for w in ai_words if w in content]
assert not found, f'AI-slop: {found}'
print(f'✅ saas-admin.html: {size}B, 5 sub-pages, no AI-slop')
"

# 确认所有新文件存在
ls -la /Users/chenye/workspace/ddw-ai-hub/frontend/saas-*.html
ls -la /Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/core/database/tenant_filter.py
ls -la /Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/core/services/tenant_service.py
```

**只有全部 PASS 才能进入最终步骤。**

---

## 最终步骤：Git 提交 + 代码审查

### 最终自检清单

```bash
cd /Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub

# 1. 静态检查
python -c "
import py_compile, os
errors = []
for root, dirs, files in os.walk('core'):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            try:
                py_compile.compile(path, doraise=True)
            except py_compile.PyCompileError as e:
                errors.append(str(e))
if errors:
    print('COMPILE ERRORS:')
    for e in errors: print(e)
    exit(1)
print(f'✅ All .py files compile OK')
"

# 2. 测试
python -m pytest tests/ -v --tb=short 2>&1 | tail -30

# 3. 去 AI 化检查（所有前端文件）
python3 -c "
import os
ai_words = ['赋能','助力','打造','闭环','护航','全方位','一站式','深度赋能','核心竞争力','底层逻辑','未来可期']
frontend_dir = '/Users/chenye/workspace/ddw-ai-hub/frontend'
for f in os.listdir(frontend_dir):
    if f.endswith('.html') and f.startswith('saas-'):
        path = os.path.join(frontend_dir, f)
        with open(path) as fh:
            content = fh.read()
        found = [w for w in ai_words if w in content]
        has_gradient = 'linear-gradient' in content
        has_shadow = 'box-shadow' in content
        status = '✅' if not found and not has_gradient and not has_shadow else '❌'
        print(f'{status} {f}: AI-slop={found}, gradient={has_gradient}, shadow={has_shadow}')
"
```

### Git 提交

```bash
cd /Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub

# 添加所有新文件和修改
git add -A

# 提交
git commit -m "feat(saas): SaaS last-mile — tenant isolation, registration, pricing, admin dashboard

Phase 0: Automatic ORM tenant filtering (SQLAlchemy events)
Phase 1: User registration API + register page + pricing page
Phase 2: Tenant admin dashboard (overview/users/apikeys/billing/settings)

All code passes self-check:
- py_compile: all .py files OK
- pytest: all tests PASS
- De-AI check: no AI-slop words, no gradients, no shadows

Design: Ant Design enterprise OA style (#1890FF, ≤2px radius)
Architecture: FastAPI + SQLAlchemy + TenantMixin + JWT
[LLM: minimax-code]"

# 确认提交
git log --oneline -3
```

---

## 输出文件清单

完成所有 Phase 后，以下文件必须存在：

```
# Phase 0
cloud-llm/ddw-ai-hub/core/database/tenant_filter.py    ← ORM 自动租户过滤
cloud-llm/ddw-ai-hub/core/services/tenant_service.py   ← 租户管理服务
cloud-llm/ddw-ai-hub/tests/test_tenant_filter.py       ← 租户过滤测试

# Phase 1
cloud-llm/ddw-ai-hub/core/api/auth.py                  ← 新增注册端点
frontend/saas-register.html                             ← 注册页面
frontend/saas-pricing.html                              ← 套餐选择页面

# Phase 2
frontend/saas-admin.html                                ← 管理后台（5 子页面）
cloud-llm/ddw-ai-hub/core/api/admin.py                 ← 管理后台 API
```

---

## 重要约束

1. **loop 自检**：每个 Phase 完成后必须运行全部自检命令，只有 PASS 才进入下一个 Phase。如果有 FAIL，修复后重新运行，不要跳过。
2. **不重复造轮子**：读取现有代码理解已有的模式（JWT、tenant_middleware、TokenQuota 等），复用而非重写。
3. **去 AI 化**：所有 HTML 页面禁止使用 AI-slop 词汇、渐变背景、box-shadow、emoji 图标。
4. **代码完整性**：每个 .py 文件必须是完整可运行的，不要 stub 或 TODO 占位符。
5. **Git 提交**：每个 Phase 完成后做一次 git commit，不要等到最后。
6. **保存路径**：所有文件保存到 `/Users/chenye/workspace/ddw-ai-hub/` 下，32G 设备会直接从这个路径读取。

## 开始执行

读完上面所有文件后，用一句话总结你对 DDW 项目架构的理解，然后从 Phase 0 开始。
