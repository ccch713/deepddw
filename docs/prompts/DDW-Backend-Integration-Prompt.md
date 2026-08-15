# DDW 后端对接 + 安全加固 — MiniMax Code 开发提示词
# 目标设备：16G Mac mini
# 预计时间：3-4 小时

---

## 任务概述

你是一个企业级 Python 全栈开发者。上一轮通宵开发已完成 8 个模块的骨架代码，本轮任务是**后端对接真实数据 + 安全加固**。所有代码保存到 `/Users/chenye/workspace/ddw-ai-hub/` 下。

## 第零步：读取上下文（必做）

```
# 上轮开发的代码（先读核心文件理解已有模式）
/Users/chenye/workspace/ddw-ai-hub/core/main.py
/Users/chenye/workspace/ddw-ai-hub/core/database/tenant_filter.py
/Users/chenye/workspace/ddw-ai-hub/core/database/models.py
/Users/chenye/workspace/ddw-ai-hub/core/api/auth.py
/Users/chenye/workspace/ddw-ai-hub/core/api/admin.py
/Users/chenye/workspace/ddw-ai-hub/core/auth/jwt.py
/Users/chenye/workspace/ddw-ai-hub/core/config.py
/Users/chenye/workspace/ddw-ai-hub/plugins/ddw_training/services/socratic_engine.py
/Users/chenye/workspace/ddw-ai-hub/plugins/ddw_training/router.py

# 插件开发规范
/Users/chenye/workspace/ddw-ai-hub/docs/DDW_Plugin_Development_Guide.md
```

**读完后用 2 句话总结你对项目架构的理解，然后才开始编码。**

---

## 任务 1：tenant_filter.py 真实实现（最高优先级）

### 问题

当前 `core/database/tenant_filter.py` 的 `install_tenant_hooks()` 是 no-op（空函数），因为 `before_flush` 和 `do_orm_execute` 是 Session 级事件，不能绑在 Engine 上。

### 解决方案

改用 **Session 级事件监听**。在每次创建新 Session 时绑定事件：

```python
from sqlalchemy import event
from sqlalchemy.orm import Session

def _on_session_created(session, transaction):
    """每个新 Session 创建时绑定租户过滤。"""
    tenant_id = get_tenant_context()
    if tenant_id is not None:
        # 为所有 TenantMixin 查询自动注入 WHERE tenant_id = ?
        @event.listens_for(session, "do_orm_execute", once=True)
        def _filter_by_tenant(orm_execute_state):
            if orm_execute_state.is_select:
                mapper = orm_execute_state.bind_mapper
                if hasattr(mapper.class_, '__tenant_aware__') and mapper.class_.__tenant_aware__:
                    orm_execute_state.statement = orm_execute_state.statement.where(
                        mapper.class_.tenant_id == tenant_id
                    )

def install_tenant_hooks(engine):
    """在 engine 的 session_factory 上绑定事件。"""
    from sqlalchemy.orm import sessionmaker
    SessionFactory = sessionmaker(bind=engine)
    event.listen(SessionFactory, "do_orm_execute", _do_orm_execute_handler)
    logger.info("Tenant hooks installed on SessionFactory")
```

### 验证

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -c "from core.database.tenant_filter import install_tenant_hooks; print('OK')"
```

---

## 任务 2：auth.py 对接真实数据库

### 问题

当前 `core/api/auth.py` 的登录/注册是 mock 实现，没有真正读写数据库。

### 要求

修改 `core/api/auth.py`，让以下端点真正工作：

```
POST /api/v1/auth/register
  - 手机号 + 验证码 + 企业名 → 创建 Tenant + User + TokenQuota → 返回 JWT
  - 验证码暂时用内存存储（dict），后续切换 Redis

POST /api/v1/auth/send-code
  - 发送验证码（暂时打印到日志，不真实发短信）
  - 60 秒倒计时防刷

POST /api/v1/auth/login
  - 手机号/账号 + 密码 → 验证 → 返回 JWT
  - 支持 admin/DDW@2026 作为默认管理员

GET /api/v1/auth/me
  - 返回当前用户信息（从 JWT 解析）
```

### 密码哈希

使用 `hashlib.sha256` 哈希（和数据库已有数据兼容）：

```python
import hashlib
def hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()
```

### 验证

```bash
cd /Users/chenye/workspace/ddw-ai-hub
# 测试注册
curl -X POST http://localhost:8500/api/v1/auth/send-code -H "Content-Type: application/json" -d '{"phone":"13800138000"}'
# 测试登录
curl -X POST http://localhost:8500/api/v1/auth/login -H "Content-Type: application/json" -d '{"phone":"admin","password":"DDW@2026"}'
```

---

## 任务 3：admin.py 对接真实数据库

### 问题

当前 `core/api/admin.py` 返回 mock 数据。

### 要求

修改 `core/api/admin.py`，让以下端点真正读写数据库：

```
GET /api/v1/admin/overview
  - 从数据库读取：租户信息、用户数、Token 用量、API 调用次数
  - 返回真实统计数据

GET /api/v1/admin/users
  - 从 users 表读取用户列表
  - 支持分页：?page=1&size=20

POST /api/v1/admin/users/invite
  - 创建新用户（手机号 + 角色）

GET /api/v1/admin/apikeys
  - 从 api_keys 表读取

POST /api/v1/admin/apikeys
  - 创建新 API Key（生成随机 key，存储 hash）

GET /api/v1/admin/billing
  - 从 subscriptions 表读取当前套餐信息
```

---

## 任务 4：培训插件对接数据库

### 问题

当前 `plugins/ddw_training/router.py` 的课程/会话数据用内存存储。

### 要求

修改 `plugins/ddw_training/router.py`，对接 `training_sessions` 和 `training_assessments` 表：

```
GET /api/v1/training/courses
  - 返回课程列表（从配置文件读取 subjects/*.yaml）

POST /api/v1/training/sessions
  - 创建培训会话（写入 training_sessions 表）

POST /api/v1/training/chat
  - 苏格拉底对话（调用 LLM Gateway，暂时用 stub）

GET /api/v1/training/progress/{user_id}
  - 查询学习进度（从 training_sessions + training_assessments 读取）

POST /api/v1/training/quiz/grade
  - 提交测验答案 → 自动评分 → 写入 training_assessments 表
```

---

## 任务 5：CORS 收紧

### 问题

`core/main.py` 第 127 行 `allow_origins=["*"]` 是安全审计发现的 Medium 级问题。

### 要求

修改 `core/main.py`，将 CORS 改为白名单：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ddw.9cio.com",
        "https://www.9cio.com",
        "http://localhost:8500",
        "http://localhost:3000",  # 开发用
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 任务 6：requirements.txt 更新

### 要求

检查 `requirements.txt`，确保包含所有需要的依赖：

```
fastapi>=0.110.0
uvicorn>=0.23.0
sqlalchemy>=2.0.0
aiosqlite>=0.19.0
pyjwt>=2.8.0
httpx>=0.24.0
pyyaml>=6.0
python-multipart>=0.0.6
```

如果文件不存在就创建，如果存在就补全缺失的。

---

## 自检清单

每个任务完成后运行：

```bash
cd /Users/chenye/workspace/ddw-ai-hub

# 1. 编译检查
python -c "
import py_compile, os
for root, dirs, files in os.walk('core'):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if f.endswith('.py'):
            py_compile.compile(os.path.join(root, f), doraise=True)
print('compile OK')
"

# 2. 导入检查
python -c "
from core.main import create_app
from core.api.auth import router as auth_router
from core.api.admin import router as admin_router
from core.database.tenant_filter import install_tenant_hooks
print('import OK')
"

# 3. pytest（如果测试文件存在）
python -m pytest tests/ -v --tb=short 2>&1 | tail -10
```

---

## Git 提交

```bash
cd /Users/chenye/workspace/ddw-ai-hub
git add -A
git commit -m "feat: backend integration — real DB + CORS + security

- tenant_filter: Session-level event hooks (real implementation)
- auth: register/login/send-code/me endpoints (real DB)
- admin: overview/users/apikeys/billing endpoints (real DB)
- training: courses/sessions/chat/progress/quiz (real DB)
- CORS: allow_origins whitelist (security fix)
- requirements.txt: complete dependency list
[LLM: minimax-code]"
```

---

## 输出文件清单

```
core/database/tenant_filter.py    （修改：真实 Session 级事件）
core/api/auth.py                  （修改：真实 DB 读写）
core/api/admin.py                 （修改：真实 DB 读写）
plugins/ddw_training/router.py    （修改：真实 DB 对接）
core/main.py                      （修改：CORS 收紧）
requirements.txt                  （新建或更新）
```

## 开始执行

读完上下文文件后，用 2 句话总结理解，然后从任务 1 开始。
