# DDW 后端对接 + 安全加固 — TASK_SPEC
# 目标：让 DDW 底座从骨架代码变成可运行的生产级系统
# 执行设备：32G Mac mini M4（本机）
# 工具：MiMo Code CLI
# 质量保障：AHE Loop（py_compile → ruff → pytest → git commit per task）

---

## 第零步：读取上下文（必做）

先读以下核心文件理解已有模式：
```
core/main.py
core/database/tenant_filter.py
core/database/models.py
core/api/auth.py
core/api/admin.py
core/auth/jwt.py
core/config.py
core/database/session.py
plugins/ddw_training/router.py
plugins/ddw_training/services/socratic_engine.py
```

读完后用 2 句话总结你对项目架构的理解，然后开始编码。

---

## 任务 1：tenant_filter.py 真实实现（最高优先级）

### 问题
当前 `core/database/tenant_filter.py` 的 `install_tenant_hooks()` 可能是 no-op。需要确认 `do_orm_execute` 事件是否真正绑到了 Session 上。

### 要求
1. 确保 `install_tenant_hooks(engine)` 能在 engine 上的 session_factory 绑定事件
2. 用 `@event.listens_for(Session, "do_orm_execute")` 或 SessionFactory 级别事件
3. 对标记了 `__tenant_aware__ = True` 的 mapper 自动注入 `WHERE tenant_id = ?`
4. `before_flush` 自动为新对象注入 tenant_id

### 验证
```bash
python -c "from core.database.tenant_filter import install_tenant_hooks; print('import OK')"
```

### AHE Loop
py_compile → ruff --select=E,W,F → 写 test → pytest

---

## 任务 2：auth.py 对接真实数据库

### 问题
当前 `core/api/auth.py` 的登录/注册可能是 mock 实现。

### 要求
修改 `core/api/auth.py`，让以下端点真正读写数据库：

```
POST /api/v1/auth/register
  - 手机号 + 验证码 + 企业名 → 创建 Tenant + User + TokenQuota → 返回 JWT
  - 验证码暂时用内存存储（dict），后续切换 Redis

POST /api/v1/auth/send-code
  - 发送验证码（暂时打印到日志，不真实发短信）
  - 60 秒倒计时防刷

POST /api/v1/auth/login
  - 手机号 + 密码 → 验证 → 返回 JWT
  - 密码用 hashlib.sha256 哈希

GET /api/v1/auth/me
  - 返回当前用户信息（从 JWT 解析）
```

### 密码哈希
```python
import hashlib
def hash_password(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()
```

### AHE Loop
py_compile → ruff → 写 test（测试注册/登录/me） → pytest

---

## 任务 3：admin.py 对接真实数据库

### 问题
当前 `core/api/admin.py` 返回 mock 数据。

### 要求
修改 `core/api/admin.py`，让以下端点真正读写数据库：

```
GET /api/v1/admin/overview
  - 从数据库读取：租户信息、用户数、Token 用量、API 调用次数

GET /api/v1/admin/users
  - 从 users 表读取用户列表，支持分页：?page=1&size=20

POST /api/v1/admin/users/invite
  - 创建新用户（手机号 + 角色）

GET /api/v1/admin/apikeys
  - 从 api_keys 表读取

POST /api/v1/admin/apikeys
  - 创建新 API Key（生成随机 key，存储 hash）

GET /api/v1/admin/billing
  - 从 subscriptions 表读取当前套餐信息
```

### AHE Loop
py_compile → ruff → 写 test → pytest

---

## 任务 4：培训插件对接数据库

### 问题
当前 `plugins/ddw_training/router.py` 的课程/会话数据用内存存储。

### 要求
修改 `plugins/ddw_training/router.py`，对接数据库表：

```
GET /api/v1/training/courses
  - 返回课程列表

POST /api/v1/training/sessions
  - 创建培训会话（写入数据库）

POST /api/v1/training/chat
  - 苏格拉底对话（调用 LLM Gateway，暂时用 stub）

GET /api/v1/training/progress/{user_id}
  - 查询学习进度

POST /api/v1/training/quiz/grade
  - 提交测验答案 → 自动评分 → 写入数据库
```

### AHE Loop
py_compile → ruff → 写 test → pytest

---

## 任务 5：CORS 收紧

### 问题
`core/main.py` 中 `allow_origins=["*"]` 是安全问题。

### 要求
修改 CORS 为白名单：
```python
allow_origins=[
    "https://ddw.9cio.com",
    "https://www.9cio.com",
    "http://localhost:8500",
    "http://localhost:3000",
]
```

### AHE Loop
py_compile → ruff → pytest

---

## 任务 6：requirements.txt 更新

### 要求
确保 `requirements.txt` 包含所有依赖：
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

---

## 任务 7：设备绑定模块（安全加固）

### 新建 `core/auth/device_binding.py`

功能：
1. `get_device_whitelist()` — 从配置/环境变量读取设备白名单
2. `verify_device(fingerprint, phone)` — 验证设备是否在白名单中
3. `_match_device(fp, device_info)` — 设备匹配逻辑

设备白名单（硬编码到配置中）：
```python
ADMIN_DEVICE_WHITELIST = {
    "32G-Mac-mini": {
        "serial": "D9CXVC9Q5L",
        "screen_hints": ["2560x1440", "1920x1080"],
    },
    "128G-MBP": {
        "serial": "C7M6MG97JL",
        "screen_hints": ["3456x2234", "2560x1600", "1728x1117"],
    },
}
```

### 修改登录流程
admin 角色登录时额外验证设备指纹：
```python
if user.role == 'admin':
    fingerprint = body.device_fingerprint or {}
    ok, reason = verify_device(fingerprint, body.phone)
    if not ok:
        raise HTTPException(403, f"设备验证失败: {reason}")
```

### AHE Loop
py_compile → ruff → 写 test → pytest

---

## 任务 8：UserBinding 模型 + API

### 在 `core/database/models.py` 添加模型
```python
class UserBinding(Base, TimestampMixin, TenantMixin):
    __tablename__ = "user_bindings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_uid: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(128), nullable=True)
    binding_type: Mapped[str] = mapped_column(String(32), default="login")
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

### 新增 API 端点
```
GET    /api/v1/user/bindings         → 查询已绑定的第三方账号
POST   /api/v1/user/bindings/wechat  → 绑定微信（生成授权链接 stub）
POST   /api/v1/user/bindings/dingtalk → 绑定钉钉（stub）
DELETE /api/v1/user/bindings/{id}     → 解绑
```

### AHE Loop
py_compile → ruff → 写 test → pytest

---

## 总体 AHE Loop 质量保障

每个任务完成后：
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
print('core compile OK')
"

# 2. Ruff 检查
ruff check core/ --select=E,W,F --fix 2>/dev/null || true

# 3. Pytest
python -m pytest tests/ -v --tb=short 2>&1 | tail -20

# 4. 每个任务单独 git commit
git add -A && git commit -m "feat(module): description"
```

## 最终验收

全部 8 个任务完成后：
```bash
cd /Users/chenye/workspace/ddw-ai-hub

# 全量编译
python -c "
import py_compile, os
count = 0
for root, dirs, files in os.walk('core'):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if f.endswith('.py'):
            py_compile.compile(os.path.join(root, f), doraise=True)
            count += 1
for root, dirs, files in os.walk('plugins'):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if f.endswith('.py'):
            py_compile.compile(os.path.join(root, f), doraise=True)
            count += 1
print(f'{count} files compile OK')
"

# 全量测试
python -m pytest tests/ plugins/ddw_training/tests/ -v --tb=short

# Ruff
ruff check core/ plugins/ddw_training/ --select=E,W,F

# Git
git log --oneline -5
```

## 输出文件清单

```
core/database/tenant_filter.py    （修改：真实 Session 级事件）
core/api/auth.py                  （修改：真实 DB 读写 + 设备验证）
core/api/admin.py                 （修改：真实 DB 读写）
core/auth/device_binding.py       （新建：设备绑定验证）
core/database/models.py           （修改：添加 UserBinding）
core/main.py                      （修改：CORS 收紧）
plugins/ddw_training/router.py    （修改：真实 DB 对接）
requirements.txt                  （更新：补全依赖）
tests/test_backend_integration.py （新建：集成测试）
```
