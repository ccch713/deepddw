# TASK_SPEC：邮箱绑定 + 邮件验证码找回密码（企业邮箱 SMTP）

> 背景：忘记密码找回机制缺失。用户拍板：新用户强制绑定企业邮箱（9cio.com 域名邮箱），忘记密码时发邮件验证码找回——替代短信（零短信费），邮件走 SMTP（阿里云免费企业邮箱，0 元）。
> 开发：MiMo Code。验收：deepseek v4 flash。部署：16G + ECS。

## 1. 需求

| # | 功能 | 说明 |
|---|---|---|
| 1 | **邮箱绑定** | User 表加 email（唯一索引）+ email_verified；**注册强制填邮箱**（RegisterReq 加 email 必填） |
| 2 | **邮件验证码发送** | core/email.py：SMTP 异步发送（smtplib + asyncio.to_thread）；验证码 6 位数字，TTL 300 秒，一次性 |
| 3 | **忘记密码找回** | POST /auth/forgot-password（邮箱+captcha）→ 发验证码邮件；POST /auth/reset-password（邮箱+验证码+新密码）→ 重置（强度校验、password_changed_at=now、email_verified=True） |
| 4 | **防滥用** | 同邮箱 60 秒 1 次；IP 每分钟 ≤10 次；email 不存在也返回 sent:true（防枚举，日志记） |
| 5 | **前端** | /ui/forgot-password.html 三步页；login.html 加"忘记密码？"链接；saas-register.html 加邮箱字段 |
| 6 | **SMTP 未配置降级** | DDW_ENV != production 且未配置 SMTP → 验证码写日志（mock，与 send-code 同模式）；production 未配置 → 503"邮件服务未配置" |

## 2. 数据模型（core/database/models.py）

```python
# User 新增
email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True, index=True)
email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

## 3. 邮件模块（新建 core/email.py）

```python
# 配置（环境变量）：
#   DDW_SMTP_HOST   默认 smtp.qiye.aliyun.com
#   DDW_SMTP_PORT   默认 465
#   DDW_SMTP_USER   (账号，如 noreply@9cio.com)
#   DDW_SMTP_PASSWORD (SMTP 授权码)
#   DDW_SMTP_SENDER (发件人，如 DDW AI HUB <noreply@9cio.com>)
# 函数：
async def send_mail(to: str, subject: str, html: str) -> bool:
    # asyncio.to_thread(smtplib.SMTP_SSL ...); 失败 logger.error 返回 False

async def send_verify_code(email: str, code: str, purpose: str) -> bool:
    # purpose: "verify_email"(注册验证) / "reset_password"(找回密码)
    # HTML 模板：中英文标题 + 验证码大字 + 5 分钟有效提示 + DDW AI HUB 签名
```

## 4. API 端点（core/api/auth.py 新增）

```python
class ForgotPasswordReq(BaseModel):
    email: str = Field(..., max_length=255)
    captcha_id: str = Field(..., min_length=8, max_length=64)
    captcha_code: str = Field(..., min_length=1, max_length=8)

class ResetPasswordReq(BaseModel):
    email: str = Field(..., max_length=255)
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=128)

@router.post("/forgot-password")
# 1) 校验图形验证码（消费）2) 邮箱 60s/次 + IP 10次/分 限流
# 3) 查 email：存在 → 生成6位码 → send_mail(reset_password)
#    不存在 → 同样返回 {"sent": True}（防枚举，日志记 email_not_found）
# 4) SMTP 未配置：production → 503；非 production → 日志打印验证码 + sent:true

@router.post("/reset-password")
# 1) _consume_code 邮箱验证码（key: ddw:verify:email:{email}，TTL 300s，一次性）
# 2) validate_password_strength(new_password)
# 3) 查用户 → 新密码 != 旧密码（verify_password 比较）
# 4) password_hash 更新 + password_changed_at=now + email_verified=True
# 5) 返回 {"reset": True}

# 注册改造（RegisterReq 加 email 必填）：
#   注册成功后发"邮箱验证"邮件（send_verify_code verify_email）
#   新增端点：POST /auth/verify-email { email, code } → email_verified=True
```

## 5. 前端

### /ui/forgot-password.html（新建，与 login 同风格 CSS 变量）

```
Step1: 邮箱输入 + 图形验证码(图片+换一张) → [发送验证码]
Step2: 6位邮件验证码 + 新密码 + 确认新密码（前端即时强度提示）→ [重置密码]
成功 → toast → 跳 /ui/login.html
```

### login.html：底部加「忘记密码？」→ /ui/forgot-password.html
### saas-register.html：注册表单加「邮箱」必填字段（maxlength=255，前端格式校验）

## 6. 数据库迁移（更新 scripts/migrate_login_security.py 幂等）

```python
if "email" not in cols: ALTER TABLE users ADD COLUMN email VARCHAR(255)
if "email_verified" not in cols: ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 0
# 存量不动（email 可空；新用户注册强制）
```

## 7. 测试（tests/test_email_reset.py，≥8 条）

```python
1. test_forgot_password_sends_code         # captcha 正确 → sent:true + 验证码可消费（monkeypatch send_mail 捕获）
2. test_forgot_password_email_not_found    # 不存在邮箱 → sent:true（防枚举）
3. test_forgot_password_requires_captcha   # 无图形验证码 → 拒绝
4. test_forgot_password_rate_limit         # 同邮箱 60s 二次 → 429
5. test_reset_password_success             # 正确验证码+强密码 → reset:true + 旧密码失效新密码可登录
6. test_reset_password_wrong_code          # 错验证码 → 400
7. test_reset_password_weak                # 弱密码 → 400
8. test_register_requires_email            # 注册无 email → 422
9. test_verify_email_endpoint              # 注册后验证邮箱 → email_verified=True
10. test_smtp_not_configured_production    # 模拟 production 未配置 SMTP → 503
```

## 8. 验收标准

1. pytest 全量全绿（新增 ≥10 条 + 既有 70 条无回归）
2. 16G（非 production）：forgot-password 发码 → 日志可见验证码 → reset-password 成功 → 新密码登录
3. ECS（production）：SMTP 配置后真实发信到指定邮箱验证；未配置返回 503
4. 前端 forgot-password.html 三页流程可用；login.html 链接存在；注册页邮箱字段存在
5. 16G + ECS 部署完成，迁移幂等

## 9. 开发约束

- 不破坏既有功能（验证码/限流/防枚举/设备绑定/密码生命周期）
- 邮箱验证码存储复用现有 _VERIFY_CODES 模式（Redis 优先 + 内存 fallback），key 用 email 前缀
- 密码哈希沿用 hash_password；强度校验复用 core/auth/password_policy.py
- 前端 CSS 变量风格；HTML 模板中文化（企业级署名：武汉锐果互动信息技术有限公司 / DDW AI HUB）
