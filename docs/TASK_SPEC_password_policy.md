# TASK_SPEC：DDW 密码生命周期补丁（自助改密 + 强度策略 + 定期更换）

> 背景：P0 登录安全上线后发现遗漏——用户自助改密、密码强度校验、定期更换（密码过期）未实现。这是用户服务基本盘，立即补齐。
> 开发：MiMo Code。验收：deepseek v4 flash（pytest + 手动）。部署：16G + ECS。

## 1. 需求

| # | 功能 | 说明 |
|---|---|---|
| 1 | **自助改密** | 所有登录用户（owner/admin/member，任何租户）登录后自助修改密码：旧密码 + 新密码 + 确认新密码 |
| 2 | **密码强度策略** | 注册与改密统一校验：≥8 位 + 必须含字母和数字 + 拒绝纯数字/纯字母/连续重复/常见弱密码 |
| 3 | **定期更换** | 密码有效期 90 天（可配置）；到期后登录成功但响应标记 must_change=true，前端强制跳转改密页；存量账号（password_changed_at 为空）首次登录同样强制改密 |
| 4 | 改密后旧密码立即失效 | 新哈希直接覆盖 |

## 2. 后端改动

### 2.1 新增 `core/auth/password_policy.py`

```python
WEAK_PASSWORDS = {"12345678", "87654321", "password", "passw0rd", "qwertyui", "asdfghjk",
                  "zxcvbnm,", "admin123", "123456789", "11111111", "abcdefgh", "abcd1234",
                  "00000000", "123123123", "a1234567", "abc12345", "66666666", "88888888"}

def validate_password_strength(pwd: str) -> Optional[str]:
    """返回 None=通过；否则返回中文错误描述。"""
    # 长度 ≥8
    # 必须含字母 + 数字
    # 不能纯字母 / 纯数字
    # 不能全部相同字符或连续递增/递减（如 11111111 / 12345678 / abcdefgh）
    # 不在 WEAK_PASSWORDS 中
```

### 2.2 `core/api/auth.py` 改动

```python
class ChangePasswordReq(BaseModel):
    old_password: str = Field(..., min_length=6, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)

@router.post("/change-password", response_model=Dict[str, Any])
async def change_password(req: ChangePasswordReq, user: Dict[str, Any] = Depends(current_user)):
    # 1) IP 限流：同 IP 1 小时内最多 5 次（Redis INCR + 内存 fallback，沿用现有模式），超限 429
    # 2) 查库拿 User：verify_password(req.old_password, user.password_hash) 失败 → 400 "原密码错误"
    # 3) validate_password_strength(req.new_password) → 失败 400 返回具体原因
    # 4) req.new_password == req.old_password → 400 "新密码不能与原密码相同"
    # 5) user.password_hash = hash_password(req.new_password)
    #    user.password_changed_at = datetime.utcnow()
    #    提交；返回 {"changed": True}
```

登录端点（login-password / login）成功后新增返回字段：

```python
# 计算 must_change
changed_at = user.password_changed_at
if changed_at is None:
    must_change = True
else:
    age_days = (datetime.utcnow() - changed_at).days
    max_days = get_settings().password_max_age_days  # 默认 90
    must_change = age_days > max_days

TokenResp 增加字段：
    password_expired: bool = False
    must_change: bool = False
```

register 端点改动：
- 密码校验改用 validate_password_strength（替换仅 min_length=8）
- 新建用户设置 password_changed_at = datetime.utcnow()

### 2.3 `core/database/models.py`

```python
# User 新增
password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

### 2.4 `core/config.py`

```python
# settings 增加（auth 段，兼容 deployment.yaml）
password_max_age_days: int = 90   # 环境变量 DDW_PASSWORD_MAX_AGE_DAYS 可覆盖
```

## 3. 前端改动

### 3.1 新增 `frontend/change-password.html`（新页面，与 login 同风格 CSS 变量）

- 表单：原密码 / 新密码 / 确认新密码 + 提交按钮
- 前端校验：两次新密码一致；新密码长度 ≥8；含字母和数字（与后端策略一致，错误即时提示）
- 提交：`POST /api/v1/auth/change-password`（带 JWT，api.js 的 DDW.api.post 自动带 token）
- 成功 → toast 提示 → 跳转 /ui/admin.html
- 失败 → 显示后端 detail
- 页面顶部显示账号手机号（调 /auth/me）

### 3.2 登录页（login.html / welcome.html）跳转逻辑

- 登录成功响应中若 `must_change === true`：
  - toast "首次登录/密码已过期，请修改密码"
  - 跳转 `/ui/change-password.html`（**不跳 admin**）
- saas-register.html：密码输入框下方加强度提示文案"至少 8 位，需包含字母和数字"

### 3.3 admin.html（可选，若结构简单）

- 顶部用户菜单加"修改密码"入口链接到 /ui/change-password.html（找不到合适位置可跳过，不阻塞验收）

## 4. 数据库迁移（更新 scripts/migrate_login_security.py，保持幂等）

```python
# users 加列
if "password_changed_at" not in cols:
    conn.execute("ALTER TABLE users ADD COLUMN password_changed_at DATETIME")
# 存量账号密码生效时间：有密码的置为 created_at，无密码的保持 NULL
conn.execute("UPDATE users SET password_changed_at = created_at WHERE password_changed_at IS NULL AND password_hash IS NOT NULL")
```

> 注：migrate 脚本已部署到 16G/ECS，本次直接更新脚本并重跑（幂等）。

## 5. 测试用例（追加到 tests/test_login_security.py 或新文件 tests/test_password_policy.py）

```python
1. test_change_password_success            # 登录拿 token → 改密成功 → 新密码可登录、旧密码失败
2. test_change_password_wrong_old          # 旧密码错 → 400 "原密码错误"
3. test_change_password_weak_new           # 新密码纯数字 → 400 强度错误
4. test_change_password_same_as_old        # 新旧相同 → 400
5. test_change_password_requires_auth      # 无 token → 401
6. test_register_sets_password_changed_at  # 注册后 password_changed_at 非空 → 登录 must_change=False
7. test_legacy_user_must_change            # password_changed_at=NULL 用户登录 → must_change=True
8. test_password_expired_must_change       # password_changed_at 超 90 天 → 登录 must_change=True
9. test_strength_rejects_weak              # validate_password_strength 单元：纯数字/纯字母/常见弱密码/连续字符 → 拒绝
```

## 6. 验收标准

1. pytest 全量全绿（新增 9 条 + 既有 61 条不回归）
2. 手动（16G）：超管 13367266625 用初始密码登录 → 响应 must_change=true → 跳改密页 → 改成自己密码 → 新密码可登录、旧密码 401
3. 16G + ECS 部署：migrate 重跑幂等 + 服务重启无报错
4. 前端 change-password.html 可访问、样式与现有页面一致（CSS 变量）

## 7. 开发约束

- 不破坏 P0 已上线功能（验证码/限流/防枚举/设备绑定）
- 密码哈希沿用 hash_password（bcrypt，不做格式变更）
- 前端保持 CSS 变量风格（var(--xxx)），不自创硬编码色值
- 所有新端点/字段中文注释
