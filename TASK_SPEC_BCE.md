# DDW B+C+E 开发任务 — TASK_SPEC
# B: 登录页设备指纹采集 JS
# C: 个人中心页面 saas-account.html
# E: JWT key 长度升级

---

## 任务 E：JWT key 长度升级（最简单，先做）

### 问题
pytest 报 `InsecureKeyLengthWarning: The HMAC key is 27 bytes long, below minimum 32 bytes`。
当前默认值在 `core/config.py` 第 139 行：`"dev-secret-change-me"`（20 字符）。

### 要求
修改 `core/config.py`，将默认 JWT secret 改为 ≥32 字节的随机字符串：

```python
# 第 139 行附近
sec = self.jwt.get("secret") or self.server.get("secret_key") or "ddw-ai-hub-default-jwt-secret-2026-change-in-production-32bytes"
```

同时检查 `.env.deploy` 或环境变量中是否有 `DDW_JWT_SECRET` 设置，如果有，保持不变。

### 验证
```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest tests/test_backend_integration.py::test_login_password -v --tb=short 2>&1 | grep -i "warning\|PASS\|FAIL"
```

---

## 任务 B：登录页密码登录 + 设备指纹采集

### 问题
当前 `frontend/saas-register.html` 只有注册功能，没有密码登录表单。后端 `core/api/auth.py` 已有 `/login-password` 端点。

### 要求
在 `frontend/saas-register.html` 中：

1. **添加登录/注册 Tab 切换**：顶部增加两个 Tab（"注册" / "登录"），点击切换表单
2. **登录表单**：手机号 + 密码 + 登录按钮
3. **设备指纹采集**：登录时自动采集浏览器设备指纹，附在请求体中

#### 设备指纹采集函数（加到 `<script>` 中）
```javascript
function getDeviceFingerprint() {
  var fp = {
    userAgent: navigator.userAgent,
    language: navigator.language,
    platform: navigator.platform,
    screen: screen.width + 'x' + screen.height,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    hardwareConcurrency: navigator.hardwareConcurrency || 0,
    deviceMemory: navigator.deviceMemory || 0
  };
  // canvas 指纹
  try {
    var c = document.createElement('canvas');
    var ctx = c.getContext('2d');
    ctx.textBaseline = 'top';
    ctx.font = '14px Arial';
    ctx.fillText('DDW-device-check', 2, 2);
    fp.canvas = c.toDataURL().slice(-50);
  } catch(e) { fp.canvas = 'unsupported'; }
  return fp;
}
```

#### 登录提交（加到登录表单的 submit handler 中）
```javascript
const payload = {
  phone: phone,
  password: password,
  device_fingerprint: getDeviceFingerprint()
};
const r = await fetch(API_BASE + '/api/v1/auth/login-password', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify(payload)
});
```

#### 设备验证失败提示
```javascript
if (!r.ok) {
  if (d.detail && d.detail.includes('设备验证失败')) {
    showMsg('请使用授权设备登录管理后台');
  } else {
    showMsg(d.detail || '登录失败');
  }
}
```

### 样式
- Tab 样式参考现有的 topbar 风格：深蓝 #001529 底，白色文字
- 登录表单复用现有 `.form-input` / `.btn-primary` 样式
- 移动端适配保持一致

### 验证
```bash
# 确认 HTML 完整
python -c "
with open('frontend/saas-register.html') as f:
    content = f.read()
assert '<!DOCTYPE html>' in content
assert '</html>' in content
assert 'getDeviceFingerprint' in content
assert 'login-password' in content
assert 'device_fingerprint' in content
print('HTML verification OK')
"
```

---

## 任务 C：个人中心页面 saas-account.html

### 要求
创建 `frontend/saas-account.html`，Ant Design 企业 OA 风格（#1890FF/#001529，圆角≤2px）。

### 页面结构

#### 顶部栏
- 复用现有 topbar 样式（logo "钜" + DDW AI Hub）
- 右上角：用户名 + 退出登录

#### 左侧导航（200px 固定宽度）
```
个人中心
├── 基本信息
├── 第三方绑定
├── 安全设置
└── 登录日志
```

#### 右侧内容区

**Tab 1: 基本信息**
- 姓名、手机号（只读）、角色、企业名
- 头像占位

**Tab 2: 第三方绑定**
- 微信：未绑定 → 显示"绑定微信"按钮 → 调用 `/api/v1/user/bindings/wechat`
- 钉钉：未绑定 → 显示"绑定钉钉"按钮 → 调用 `/api/v1/user/bindings/dingtalk`
- 飞书：未绑定 → 显示"绑定飞书"按钮（灰显，提示"即将上线"）
- 每个已绑定的显示：昵称 + 绑定时间 + 解绑按钮

**Tab 3: 安全设置**
- 修改密码：旧密码 + 新密码 + 确认新密码
- 设备绑定信息：当前设备是否在白名单中
- 管理员可见：设备白名单列表

**Tab 4: 登录日志**
- 最近 20 条登录记录（时间 + IP + 设备 + 状态）
- 暂用 mock 数据

### API 调用
```javascript
// 查询已绑定账号
GET /api/v1/user/bindings
Authorization: Bearer {token}

// 绑定微信
POST /api/v1/user/bindings/wechat
Authorization: Bearer {token}

// 绑定钉钉
POST /api/v1/user/bindings/dingtalk
Authorization: Bearer {token}

// 解绑
DELETE /api/v1/user/bindings/{id}
Authorization: Bearer {token}

// 查询用户信息
GET /api/v1/auth/me
Authorization: Bearer {token}
```

### 样式规范（DDW 前端设计标准 v5）
- 主色：#1890FF（蓝），辅色：#001529（深蓝）
- 圆角：≤2px，无阴影，无渐变
- 字体：-apple-system, "PingFang SC", "Microsoft YaHei"
- 按钮：实色背景，hover 加亮
- 卡片：1px solid #E8E8E8 边框
- 禁止 emoji、禁止 AI 风格（无 rounded-xl、无 shadow-lg、无 gradient）
- Footer 必须包含：© 2026 武汉锐果互动 + ICP + 公安备案

### 验证
```bash
python -c "
with open('frontend/saas-account.html') as f:
    content = f.read()
assert '<!DOCTYPE html>' in content
assert '</html>' in content
assert 'getDeviceFingerprint' not in content  # 不应有（这是登录页的）
assert '第三方绑定' in content or 'bindings' in content
assert '1890FF' in content
assert '鄂ICP备' in content
print('Account page verification OK')
"
```

---

## Git 提交

三个任务各自一个 commit：
```bash
# E
git add core/config.py && git commit -m "fix(auth): upgrade default JWT secret to 32+ bytes"

# B
git add frontend/saas-register.html && git commit -m "feat(frontend): add password login + device fingerprint to register page"

# C
git add frontend/saas-account.html && git commit -m "feat(frontend): add personal account center page with bindings"
```

---

## 执行顺序
1. E（JWT key）— 最简单，1 分钟
2. B（登录页改造）— 中等，5 分钟
3. C（个人中心页）— 最复杂，10 分钟

每个任务完成后：py_compile + 验证脚本 + git commit。
