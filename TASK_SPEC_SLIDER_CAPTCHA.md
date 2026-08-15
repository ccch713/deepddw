# TASK_SPEC：DDW AI Hub 登录验证码 → 拼图滑块验证（AJ-Captcha 开源设计移植）

> 紧急程度：P0（今天客户要看 demo，当前登录被验证码死循环卡死）
> 执行者：MiMo Code CLI（mimo run headless）
> 验收者：Hermes（本 spec 末尾验收标准逐条核验）

---

## 一、背景与根因

**现状问题（已定位）**：
1. **登录死循环（P0 阻塞）**：多租户用户（如 13797078252 江昆鹏）登录时：
   - 第一次提交 → 后端 `verify_captcha()` **消费验证码**（`_invalidate_captcha` 删除）→ 返回 409 MULTI_TENANT + 租户列表
   - 前端弹出租户选择 → 用**同一个已消费的验证码**再次提交 → 400「验证码错误或已过期」
   - **用户永远无法登录**。这是"登录进不去"的根因。
2. **体验差**：图片验证码输入反人类（用户原话："验证码这个不是很好"）。
3. **需求**：改为**拼图滑块验证**（拖动滑块拼图对齐缺口），参考 GitHub 最流行开源项目 **AJ-Captcha（anji-plus/captcha）** 的设计移植到 Python/Pillow 实现。零第三方依赖、零成本（符合用户 2026-08-03 否决 hCaptcha 类第三方验证码的红线）。
4. 密码输入框加显示/隐藏切换图标（用户需求1）。
5. 多租户选择弹窗改为独立模态框（用户需求4，"反人类"界面改版）。

## 二、实现方案

### 2.1 新文件 `core/auth/slider_captcha.py`（Pillow 实现，参考 AJ-Captcha 拼图滑块）

```
目录结构：
ddw-ai-hub/
├── core/
│   ├── auth/
│   │   ├── slider_captcha.py     ← 新增（滑块生成/校验，~250行）
│   │   └── captcha.py            ← 保留（register/send-code 仍用图片验证码）
│   └── api/
│       └── auth.py               ← 改造（login-password 换滑块校验 + 2个新端点）
├── frontend/
│   ├── login.html                ← 改造（滑块组件 + 密码图标 + 模态框）
│   └── assets/js/slider-captcha.js  ← 新增（滑块前端逻辑，~200行）
└── tests/
    └── test_slider_captcha.py    ← 新增（7条用例）
```

### 2.2 后端 API 设计

```python
# 新增端点（core/api/auth.py 内，router prefix = /api/v1/auth）

# 1. 获取滑块拼图
GET /api/v1/auth/slider
→ 200 {
    "captcha_id": "uuid4-hex",          # 长度 32
    "bg_image": "data:image/png;base64,...",      # 320x160 背景图（带缺口）
    "puzzle_image": "data:image/png;base64,...",  # 50x50 拼图块（透明底）
    "x_range": [60, 240]                # 缺口 x 坐标合法范围（前端滑块轨道约束）
}
# 存储：Redis ddw:slider:{captcha_id} → 真实 x_target，TTL 120s；Redis 不可用降级内存 dict（复用 captcha.py 的 _get_redis 模式）

# 2. 校验滑块位置
POST /api/v1/auth/slider/verify
Body: {"captcha_id": str, "x": int}
→ 200 {"token": "slider-token-uuid"}   # 一次性 token，Redis ddw:slider_token:{token} → captcha_id，TTL 300s
→ 400 {"detail": "验证失败，请重试"}     # |x - x_target| > 5px 或 captcha 无效/过期
→ 429 {"detail": "验证失败次数过多，请稍后再试"}  # 同 IP 3 次失败后 60s 冷却

# 3. login-password 改造
POST /api/v1/auth/login-password
Body: {
    "phone": str,
    "password": str,
    "slider_token": str,       # ← 新增（替代 captcha_id + captcha_code）
    "tenant_id": Optional[int] # 多租户二次提交时携带
}
→ 200 TokenResp（同现有）
→ 409 MULTI_TENANT + tenant 列表（同现有，**注意：此时 slider_token 不消费**）
→ 400/401/429 同现有
```

### 2.3 核心逻辑（slider_captcha.py）

```python
SLIDER_TTL = 120        # 拼图有效期
SLIDER_TOKEN_TTL = 300  # 校验通过后 token 有效期
SLIDER_TOLERANCE = 5    # 容差 px
MAX_FAILS = 3           # 同 IP 失败 3 次作废 + 冷却 60s

def generate_slider() -> (captcha_id, bg_base64, puzzle_base64, x_target):
    """用 Pillow 生成拼图滑块：
    1. 320x160 背景：随机渐变 + 随机几何图形（圆形/多边形/线条）+ 随机色相
    2. 50x50 拼图块：从背景挖出（位置 x_target 随机 60~240, y 随机 20~90）
       缺口边缘加 2px 深色阴影 → 生成独立透明 PNG（拼图块）
       背景图在缺口位置填灰白色块 + 阴影（模拟 AJ-Captcha 视觉）
    3. 返回 base64 data URL（PNG）
    """

def verify_slider(captcha_id, x, ip) -> (ok: bool, reason: str, token: str|None):
    """校验：|x - x_target| <= 5px 即通过。
    通过 → 生成 token 存 Redis（TTL 300s），删除滑块记录 → 返回 token
    失败 → 计数，3 次后作废滑块 + IP 冷却 60s
    """

def consume_slider_token(token, ip) -> bool:
    """login-password 调用：
    - token 存在且未过期 → 返回 True（**不删除**，多租户 409 后二次提交仍可用）
    - 登录最终成功（签发 JWT）后调用 revoke_slider_token(token) 删除
    """

def revoke_slider_token(token):
    """登录成功后消费 token（删除 Redis key）"""
```

**关键设计（修复死循环）**：`consume_slider_token` 不消费 token，只在登录**成功签发 JWT 后**才 `revoke`。这样多租户 409 → 选租户 → 二次提交同一 token → 仍然有效 → 登录成功。

### 2.4 login-password 改造点（core/api/auth.py 第 847-858 行）

```python
# 原：ok, reason = verify_captcha(req.captcha_id, req.captcha_code, ip)
# 新：
if not consume_slider_token(req.slider_token, ip):
    await _write_login_audit(..., reason="滑块验证无效")
    raise HTTPException(400, "请先完成滑块验证")
# ... 后续四层限流/防枚举/密码校验/设备绑定逻辑不变 ...
# 在签发 JWT 成功返回前：
revoke_slider_token(req.slider_token)
```

Pydantic 模型：
```python
class SliderVerifyReq(BaseModel):
    captcha_id: str = Field(..., min_length=8, max_length=64)
    x: int = Field(..., ge=0, le=320)

class SliderVerifyResp(BaseModel):
    token: str

class LoginPasswordReq(BaseModel):  # 改造
    phone: str = Field(..., pattern=r"^1\d{10}$")
    password: str = Field(..., min_length=6, max_length=128)
    slider_token: str = Field(..., min_length=16, max_length=128)  # ← 替代 captcha_id/captcha_code
    tenant_id: Optional[int] = None
```

### 2.5 前端 login.html 改造

1. **滑块组件**（替换现有 `.captcha-row` 验证码输入区，保留相同位置和 CSS 变量风格）：
   - `<canvas>` 绘制背景图（带缺口），滑块轨道在 canvas 下方，拖动手柄
   - 拖动结束 → canvas 上画拼图块跟随 → 松手时读取 x → POST /auth/slider/verify
   - 成功：拼图块吸附到位 + 绿色对勾动画，token 存入 `currentSliderToken`，登录按钮可用
   - 失败：滑块弹回原位 + 红色提示「验证失败，请重试」+ 自动刷新拼图（最多自动重试 1 次，避免骚扰）
   - 点击拼图图片可刷新（换一张）
2. **密码显示/隐藏图标**：密码框右侧 SVG 眼睛图标（非 emoji），点击切换 type=password/text
3. **多租户选择弹窗改版**：独立居中模态框（遮罩 + 卡片 + 动画），选项显示租户名 + 角色徽章（admin/owner 彩色标签），选中高亮，点击「确认并登录」→ 携带同一 slider_token + tenant_id 重新提交
4. 提交登录时：`slider_token: currentSliderToken`（不再提交 captcha_id/captcha_code）

### 2.6 测试用例（tests/test_slider_captcha.py，7 条）

```python
# 1. test_slider_generate：GET /api/v1/auth/slider → 200，返回 captcha_id(32hex)/bg_image(data:image/png)/puzzle_image/x_range[60,240]
# 2. test_slider_verify_ok：mock 生成后取真实 x_target（测试内直接调 generate_slider 拿 x_target）→ POST verify x=x_target → 200 + token
# 3. test_slider_verify_wrong：x 偏差 50px → 400
# 4. test_slider_verify_tolerance：x 偏差 4px（容差内）→ 200
# 5. test_login_password_with_slider_token：有效 token + 正确密码 → 200 JWT；登录成功后 token 被 revoke，再次使用 → 400
# 6. test_login_password_multitenant_no_consume：模拟 MULTI_TENANT 场景：第一次提交（有效 token + 正确密码 + 无 tenant_id）→ 409；第二次提交（同一 token + tenant_id）→ 200（死循环修复验证）
# 7. test_slider_fail_limit：同 IP 错 3 次 → 第 4 次即使 x 正确也 429 + 滑块作废
```

## 三、验收标准（Hermes 逐条核验）

| # | 验收项 | 方法 |
|---|--------|------|
| A | pytest 全绿：新增 7 条 + 原有全部通过 | `cd ddw-ai-hub && python3 -m pytest tests/ -x -q` |
| B | 登录页滑块可拖动、拼图可对齐、验证通过有反馈 | 浏览器打开 `/ui/login.html` 实操 |
| C | 单租户账号（如 13437298311 / Demo@2026ddw）滑块 + 密码登录成功 | 浏览器实操 |
| D | **多租户账号（13797078252 / Jkp@2026ddw）完整流程：滑块 → 409 弹窗 → 选租户 → 登录成功** | 浏览器实操（死循环修复核心验证） |
| E | 密码框有显示/隐藏图标且可切换 | 浏览器实操 |
| F | 多租户弹窗为独立居中模态框（非错误提示区） | 浏览器实操 |
| G | 旧图片验证码端点 /api/v1/auth/captcha 仍可用（register/send-code 不回归） | curl |
| H | 部署 ECS 后公网 ddw.9cio.com 登录可用 | rsync + systemctl restart ddw-core + 公网验证 |

## 四、约束与红线

1. **只改 login 相关**：login-password 用滑块；`register`/`send-code`/`sms` 等仍用图片验证码（captcha.py 保留，不删除）
2. **零新依赖**：只用 Pillow（已装 10.4.0）+ FastAPI + Redis（可降级内存）——禁止引入第三方验证码 SDK
3. **Redis 降级**：全部沿用 captcha.py 的 `_get_redis()` 模式（Redis 不可用 → 内存 dict）
4. **安全基线保留**：四层限流（IP+账号 5次/15min、IP 全局 20次/30min、账号 10次/1h 锁定、滑块 L0 3次作废）、防枚举（统一 401 + 虚拟 bcrypt）、设备绑定、login_audit 全保留
5. **前端视觉**：沿用 login.html 现有 CSS 变量（--brand/--border 等），不要改页面整体风格
6. **git 提交**：完成后 `git add` 相关文件 + commit `feat(slider-captcha): 登录验证码改拼图滑块+修复多租户死循环 [LLM: mimo-code]`，**不要 push**（Hermes 验收后统一处理）
7. 不要动 ECS 上的文件（本地开发完成后 Hermes 负责同步部署）
