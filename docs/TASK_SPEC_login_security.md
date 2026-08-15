# TASK_SPEC：DDW 登录安全闭环 P0（验证码 + 防爆破 + 设备绑定红线）

> 开发：MiMo Code（mimo run）。验收：deepseek v4 flash 独立执行（pytest + grep + 手动验证）。
> 铁律：本 spec 描述的需求与现有代码差异点必须逐条实现；不得删除现有功能；所有改动必须配套 pytest。

---

## 1. 背景

DDW AI Hub 登录体系现状：`core/api/auth.py` 只有 send-code（短信 mock）/ register / login / login-password / me。
问题：①无图形验证码，可脚本爆破 ②login-password 对不存在用户返回 404（用户枚举）③无失败锁定 ④前端 login.html 调用旧端点（/auth/sms/request、/auth/pin/login）已断链 ⑤前端存在万能码 8888/dev_code 文案泄露 ⑥设备绑定是全局强制且前端不采集指纹（形同虚设）。

本任务实现零成本验证码闭环 + 四层防爆破 + 账号级设备绑定（红线）。

## 2. 现有代码基线（必须兼容）

| 文件 | 现状 |
|---|---|
| `core/api/auth.py` | send-code/register/login/login-password/me；`_VERIFY_CODES` 内存 + Redis 双写；`_rate_limit_send_code`；`ALWAYS_ACCEPT_CODE` 环境变量；bcrypt 哈希（sha256 预哈希 rounds=12） |
| `core/auth/device_binding.py` | 全局白名单 `ADMIN_DEVICE_WHITELIST`（32G-Mac-mini: D9CXVC9Q5L / 128G-MBP: C7M6MG97JL），`verify_device(fingerprint, phone)` 返回 (ok, reason)；匹配规则：serial 完全匹配 或 screen_resolution ∈ screen_hints |
| `core/database/models.py` | `User`(phone unique/password_hash/name/role owner|admin|member/status/last_login_at)；`UserBinding`(user_id/provider/uid/...)；`TenantMixin` 租户过滤 |
| `core/config.py` | `mode` 配置（standalone 时跳过设备验证）；`get_settings()` |
| `frontend/login.html` | 短信/PIN 双 tab，调 `/auth/sms/request`、`/auth/sms/verify`、`/auth/pin/login`（全部 404 断链） |
| `frontend/welcome.html` / `frontend/saas-register.html` | 调新版端点但无验证码；saas-register.html:108 有"开发环境万能码：8888"；welcome.html:314 alert 万能码 |
| `frontend/js/api.js` | `DDW.api` 封装，BASE=/api/v1，`getToken/setToken/clearToken` |
| 部署 | 16G(192.168.1.7:8500) 无 Redis；ECS 生产；Python ≥3.11；venv 依赖安装用 pip |

## 3. 目录结构（新增/修改）

```
core/auth/captcha.py            # 新增：图片验证码生成/校验（captcha 库）
core/api/auth.py                # 修改：验证码端点、四层限流、防枚举、注册改造、send-code 前置、login_audit 写入、账号级设备绑定接入
core/auth/device_binding.py     # 修改：账号级绑定（保留现有全局白名单函数兼容）
core/database/models.py         # 修改：User 加 device_required/device_allowlist(JSON)；新增 LoginAudit 模型
frontend/js/fingerprint.js      # 新增：浏览器设备指纹采集（canvas+webgl+screen+ua+时区 → sha256）
frontend/login.html             # 修改：验证码组件+新端点+指纹+统一错误+倒计时+记住账号
frontend/welcome.html           # 修改：同上（登录部分）
frontend/saas-register.html     # 修改：同上（注册部分）+删万能码文案
tests/test_login_security.py    # 新增：≥12 条 pytest
requirements.txt                # 修改：加 captcha、Pillow
```

## 4. 数据模型变更（SQLAlchemy）

```python
# User 表新增字段
device_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)      # 超管账号强制设备验证
device_allowlist: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)              # 允许设备指纹列表

# 新增 LoginAudit 表（TenantMixin 不需要，全局审计）
class LoginAudit(Base):
    __tablename__ = "login_audit"
    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    ip: Mapped[Optional[str]] = mapped_column(String(45), nullable=True, index=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    method: Mapped[str] = mapped_column(String(20), default="password", nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fail_reason: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False, index=True)
```

## 5. Pydantic 模型（auth.py）

```python
class CaptchaResp(BaseModel):
    captcha_id: str
    image_base64: str          # data:image/png;base64,...
    expires_in: int = 120

class LoginPasswordReq(BaseModel):   # 改造
    phone: str = Field(..., min_length=11, max_length=20)
    password: str = Field(..., min_length=6, max_length=128)
    captcha_id: str = Field(..., min_length=8, max_length=64)
    captcha_code: str = Field(..., min_length=1, max_length=8)
    device_fingerprint: Optional[Dict[str, Any]] = None

class RegisterReq(BaseModel):        # 改造：去短信验证码
    phone: str = Field(..., min_length=11, max_length=20)
    password: str = Field(..., min_length=8, max_length=128)   # 8 位起
    captcha_id: str = Field(..., min_length=8, max_length=64)
    captcha_code: str = Field(..., min_length=1, max_length=8)
    company_name: Optional[str] = Field(None, max_length=200)
    name: Optional[str] = Field(None, max_length=120)
    plan: str = Field("free", pattern="^(free|standard|enterprise)$")

class SendCodeReq(BaseModel):        # 改造：前置图形验证码
    phone: str = Field(..., min_length=11, max_length=20)
    captcha_id: str = Field(..., min_length=8, max_length=64)
    captcha_code: str = Field(..., min_length=1, max_length=8)
```

## 6. API 端点

```
GET  /api/v1/auth/captcha
     → 200 {"captcha_id": "uuid4-hex", "image_base64": "data:image/png;base64,...", "expires_in": 120}
     生成 4 字符验证码（字符集：23456789ABCDEFGHJKLMNPQRSTUVWXYZ，去 0/O/1/I/L/S/5/Z/2 混淆对）
     存储：Redis key "ddw:captcha:{captcha_id}" TTL 120s；Redis 不可用 → 内存 dict（同 auth.py 现有 _VERIFY_CODES 模式）
     图片：captcha 库 ImageCaptcha(width=130, height=42)，字体默认，PNG base64

POST /api/v1/auth/login-password  （改造）
     请求体见 LoginPasswordReq；先校验 captcha（失败 400 "验证码错误或已过期" + 计入失败），再走限流，再查用户
     用户不存在 → 401 "账号或密码错误"（不再 404）+ 虚拟 bcrypt 校验（时间均衡）
     密码错 → 401 "账号或密码错误"
     device_required=True 的用户 → verify_device 强制（所有 mode 生效，不再跳过 standalone）
     成功 → JWT（沿用现有 create_access_token）

POST /api/v1/auth/register  （改造：去短信验证码）
     校验 captcha → 查重 → 建 Tenant+User(owner, active)+TokenQuota（复用现有逻辑）
     密码哈希沿用 hash_password

POST /api/v1/auth/send-code  （改造：前置 captcha）
     先校验 captcha（失败 400）→ 再走现有 60s 限流 → 生成码写存储（保留现有 mock 日志）
     响应不再回显 dev_code（仅当 ALWAYS_ACCEPT_CODE 环境变量存在时保留 always_accept 字段，见验收项）

POST /api/v1/auth/login  （短信登录，保留现有逻辑 + 前置 captcha 校验 + 防枚举统一 401）

限流错误响应：HTTP 429 {"detail": "..."} + header Retry-After: 秒数
```

## 7. 四层限流核心逻辑（新模块 core/api/auth.py 内或 core/auth/rate_limit.py）

```python
# 存储：Redis INCR/EXPIRE 优先；redis 不可用降级内存 dict（现有 _rate_limit_send_code 模式复用）
# 计数键：
#   L0 验证码错误：ddw:captcha_fail:{ip}:{captcha_id}  —— 连续 3 次错误 → 该 captcha_id 作废 + 60s 内拒绝同 IP 再换码
#   L1 IP+账号：  ddw:brute:{ip}:{phone}   5min 窗口 5 次失败 → 锁 15min（键 ddw:lock:{ip}:{phone} TTL 900）
#   L2 IP 全局：  ddw:brute:{ip}:global    5min 窗口 20 次失败 → 锁 30min（键 ddw:lock:{ip}:global TTL 1800）
#   L3 账号：     ddw:brute:{phone}        1h 窗口 10 次失败 → 锁 1h（键 ddw:lock:{phone} TTL 3600 + 写 users 表 locked_until）
# 失败计数仅在"密码错误/用户不存在"时递增；验证码错误走 L0 独立计数
# 命中锁 → 429 + Retry-After + detail 文案（"安全限制：请 X 分钟后重试"）
# 成功登录 → 清除该 phone/ip 的失败计数
```

## 8. 账号级设备绑定（红线，最高优先级）

```python
# core/auth/device_binding.py 改造：
# 1) 保留 verify_device() 现有签名与全局白名单（兼容旧调用）
# 2) 新增 verify_user_device(user, fingerprint) -> (ok, reason)
#    逻辑：
#      a. 若 user.device_required 为 False → 直接 (True, "no device restriction")
#      b. 若 user.device_allowlist 存在且非空 → 只匹配 allowlist（fingerprint 的 serial 或 screen_resolution）
#      c. 否则回退全局 ADMIN_DEVICE_WHITELIST
# 3) auth.py login-password/login 中：
#      if user.device_required:
#          ok, reason = verify_user_device(user, req.device_fingerprint or {})
#          if not ok: raise 403 "设备验证失败: {reason}"   ← 任何部署模式都执行，不再判断 mode
#      （删除现有 "if role in (owner,admin) and mode != standalone" 的全局强制逻辑）
```

## 9. 前端规格（三页统一）

```html
<!-- fingerprint.js：页面加载时采集，注入 window.DDW_FINGERPRINT -->
{
  serial_number: null,                       // 浏览器不可得，置 null
  screen_resolution: `${screen.width}x${screen.height}`,
  canvas_hash: <sha256 of canvas 指纹>,      // 2D canvas 渲染文字取像素 hash
  webgl_hash: <sha256 of webgl 参数>,        // 可选
  user_agent: navigator.userAgent,
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  fingerprint_hash: sha256(canvas+webgl+screen+ua+tz 组合)
}
<!-- 登录请求体携带 device_fingerprint: window.DDW_FINGERPRINT -->
```

- 验证码组件：图片 img + "换一张"链接；加载/刷新调 `GET /auth/captcha`；输入框 maxlength=4；校验失败自动刷新验证码
- 错误提示：统一使用后端 detail；429 时显示倒计时（Retry-After）
- login.html：删除短信/PIN 双 tab 的旧调用，改为"手机号+密码+验证码"单表单 + 底部"短信登录（演示）"入口保留调新版端点
- 记住账号：checkbox → localStorage 存 phone，加载自动填充
- saas-register.html：删除 `开发环境万能码：8888`（:108）与 dev_code 提示（:225）
- welcome.html：删除 `alert('验证码已发送（开发模式万能码：8888）')`（:314）与 dev_code console（:312-313）
- login.html：删除 `Dev Code:` toast（:133-134）
- 所有页面：`if (d.dev_code) ...` 分支删除（不再依赖 dev_code）

## 10. 测试用例（tests/test_login_security.py，≥12 条，必须全部可独立运行）

```python
# conftest 沿用现有测试库隔离模式（内存 SQLite / 临时库）
1. test_captcha_create_and_verify           # GET /auth/captcha 返回 id+base64；用内部函数校验答案成功
2. test_captcha_wrong_code_rejected         # 错码 → 400 + 错误计数 +1
3. test_captcha_expired_rejected            # 过期/不存在 captcha_id → 400
4. test_captcha_3_fails_invalidates         # 连续 3 次错 → 该 id 作废 + 同 IP 60s 内换码被拒(429)
5. test_login_success_with_captcha          # 正确验证码+正确密码 → 200 token
6. test_login_missing_captcha_rejected      # 无验证码 → 400
7. test_login_user_not_found_401            # 不存在用户 → 401 "账号或密码错误"（非 404）
8. test_login_5_failures_lock_15min         # 同 IP+phone 5 次失败 → 429 锁定 + Retry-After
9. test_login_account_lock_1h               # 同 phone 1h 内 10 次失败 → 429 且 users.locked_until 已写
10. test_register_without_sms               # 手机号+密码(8位)+验证码 → 201 建租户+owner
11. test_register_weak_password_rejected    # 密码 <8 位 → 422
12. test_send_code_requires_captcha         # send-code 无验证码 → 400
13. test_superadmin_device_required         # device_required=True 用户 + 非白名单指纹 → 403；白名单指纹 → 200
14. test_normal_user_no_device_required     # device_required=False 用户无指纹 → 正常登录（不卡客户）
15. test_frontend_no_magic_code             # grep 前端目录无 "8888|万能码|dev_code"（用 Path 扫描断言）
```

## 11. 验收标准（deepseek v4 flash 独立执行）

1. `pytest tests/ -v` 全绿（含新增 15 条 + 现有回归不破）
2. `grep -rn "8888\|万能码\|dev_code" frontend/` 0 命中（api.js 若含 dev_code 处理逻辑一并清理）
3. 16G 部署（scp 代码 + pip install captcha pillow + 重启 launchd com.ddw.ddw-ai-hub.16g）后手动验证：
   - 登录页显示验证码、可"换一张"、输错提示、错 5 次锁 15 分钟倒计时
   - login.html 走 /api/v1/auth/login-password 不再 404
   - 超管账号（device_required=True）非白名单设备指纹 → 403
4. 16G/ECS 环境变量确认无 DDW_ALWAYS_ACCEPT_CODE（ssh 检查）
5. 现有测试套件全量回归（pytest tests/）通过
6. 代码提交 Gitea（commit message 规范）

## 12. 开发约束

- 不删除现有功能（短信 mock 登录保留但加前置 captcha；ALWAYS_ACCEPT_CODE 逻辑保留但响应不回显 dev_code 除非环境变量显式设置）
- 不修改 tenant_filter / JWT 签发逻辑 / bcrypt 哈希格式（存量账号兼容）
- captcha 库依赖 `captcha`（自动带 Pillow）；requirements.txt 加 `captcha>=0.5` 与 `Pillow>=10`
- Redis 不可用必须优雅降级（进程内不崩、不阻塞、logger.warning 一次）
- 前端保持现有设计风格（CSS 变量 var(--xxx)，不自创硬编码色值）
- 所有新端点/字段加中文注释
