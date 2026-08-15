# 问渠 × 社会化登录整合提示词（ZCode 用）

你是 DDW AI Hub 的高级前端 + Python 全栈工程师。任务：**让问渠学生/家长/老师都能用微信/QQ/钉钉/飞书扫码登录，零密码进入问渠学习**。

核心原则：**尽量降低所有用户登录时的输入次数**。扫码 = 零输入，比手机号+密码+验证码短得多。

---

## 第一步：深度阅读以下文件

### 1.1 ddw_social_login 插件（已有，需改造）

| # | 文件 | 看什么 |
|---|---|---|
| A | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_social_login/router.py` | **第69行** `redirect_uri = "/pal.html"` 硬编码 — 这是改造核心，需要支持 `next` 参数让问渠指定回调跳转页 |
| B | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_social_login/services.py` | `handle_callback()` 完整流程：state校验→OAuth换token→解析/注册→签JWT→302。`auto_register_social_user()` 自动注册逻辑（phone占位格式 `wx_{openid[:16]}`） |
| C | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_social_login/schemas.py` | Pydantic 模型定义 |
| D | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_social_login/config_manager.py` | 通道配置读写 |
| E | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_social_login/manifest.yaml` | `config_schema` 里 `enabled_channels` / `auto_register` / `default_tenant_id` |
| F | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_social_login/TASK_SPEC.md` | 完整 TASK_SPEC（已有） |

### 1.2 问渠前端（需要加扫码按钮）

| # | 文件 | 看什么 |
|---|---|---|
| G | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/frontend/wenqu/login.html` | 问渠学生登录页（cinnabar主题、KaiTi字体、400px卡片布局）。**需要在登录按钮下方加"微信扫码登录"按钮区** |
| H | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/frontend/wenqu/student.html` | 问渠学生主页面 |
| I | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/frontend/wenqu-student.html` | 问渠学生端完整页面（2146行） |

### 1.3 DDW 底座登录（参考但不改）

| # | 文件 | 看什么 |
|---|---|---|
| J | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/frontend/login.html` | DDW 主登录页 — 已加社会化登录按钮区（参考样式和JS逻辑） |
| K | `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/core/api/auth.py` | `/auth/login-password` 端点 — 问渠密码登录也走这里 |

---

## 第二步：改造方案（3 个文件）

### 改动1：ddw_social_login router.py — callback 支持 `next` 参数

**现状**：callback 302 硬编码跳 `/pal.html`
**目标**：支持 `?next=/wenqu/student.html` 参数，允许问渠指定登录后跳转页

```python
# router.py 第56-72行改造：

@router.get("/callback/{provider}")
async def callback(
    provider: str,
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    next: str = Query(default="/pal.html"),  # 新增：登录后跳转页
    config_manager: ConfigManager = Depends(get_config_manager),
):
    result = await handle_callback(provider, code, state, request, config_manager)
    
    # 安全校验：next 必须是本站相对路径，防止开放重定向
    if not next.startswith("/") or "://" in next:
        next = "/pal.html"
    
    token_data = json.dumps(result["user"], ensure_ascii=False)
    url = f"{next}#access_token={result['access_token']}&user={token_data}"
    return RedirectResponse(url, status_code=302)
```

同时改造 `/auth/{provider}` 端点，把 `next` 参数存入 state 缓存：

```python
@router.get("/auth/{provider}")
async def auth_redirect(
    provider: str,
    request: Request,
    next: str = Query(default="/pal.html"),  # 新增
    config_manager: ConfigManager = Depends(get_config_manager),
):
    # ... 现有逻辑 ...
    state = str(uuid4())
    # state 缓存里存 next
    cache[state] = {"provider": provider, "created_at": now, "next": next}
    # ... 现有逻辑 ...
```

callback 里从 state 缓存读取 next：
```python
cached = cache.pop(state, {})
next_url = cached.get("next", "/pal.html")
```

### 改动2：问渠登录页 frontend/wenqu/login.html — 加扫码按钮

在现有登录表单的 `</form>` 之后，按钮区之前，加：

```html
<!-- 社会化登录区 -->
<div id="social-section" style="margin-top:24px;text-align:center;display:none">
  <div style="position:relative;margin-bottom:16px">
    <hr style="border:none;border-top:1px solid var(--paper-2)">
    <span style="position:absolute;top:-10px;left:50%;transform:translateX(-50%);background:var(--white);padding:0 12px;font-size:12px;color:var(--ink-3)">其他登录方式</span>
  </div>
  <div id="social-btns" style="display:flex;justify-content:center;gap:12px;flex-wrap:wrap">
    <!-- JS 动态渲染 -->
  </div>
</div>

<script>
(async function(){
  try {
    const r = await fetch('/api/v1/plugins/ddw-social-login/channels');
    if (!r.ok) return;
    const channels = await c.json();
    const enabled = channels.filter(c => c.enabled);
    if (!enabled.length) return;
    document.getElementById('social-section').style.display = 'block';
    const box = document.getElementById('social-btns');
    const icons = {wechat_open:'微信',qq:'QQ',dingtalk:'钉钉',feishu:'飞书'};
    enabled.forEach(ch => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn-social';
      btn.textContent = icons[ch.provider] || ch.display_name;
      btn.style.cssText = 'padding:10px 24px;border:1px solid var(--paper-2);border-radius:var(--radius);background:var(--white);cursor:pointer;font-size:14px;color:var(--ink);transition:all .2s';
      btn.onmouseenter = ()=> btn.style.borderColor='var(--cinnabar)';
      btn.onmouseleave = ()=> btn.style.borderColor='var(--paper-2)';
      // next 参数指向问渠学生页
      btn.onclick = ()=> location.href = `/api/v1/plugins/ddw-social-login/auth/${ch.provider}?next=/wenqu/student.html`;
      box.appendChild(btn);
    });
  } catch(e) {}
})();
</script>
```

问渠登录页的样式要和 cinnabar 主题保持一致（按钮圆角10px、hover 变 cinnabar 边框、font-family var(--font)）。

### 改动3：auto_register 角色映射

**现状**：`services.py` 自动注册时 `role="member"`
**目标**：问渠扫码用户默认 `role="student"`

在 `manifest.yaml` 的 `config_schema` 加一个配置项：

```yaml
config_schema:
  type: object
  properties:
    # ... 现有配置 ...
    default_role:
      type: string
      default: "member"
      description: "自动注册用户的默认角色。问渠部署时设为 student"
```

在 `services.py` 的 `auto_register_social_user()` 里读取：

```python
async def auto_register_social_user(session, provider, social_user, config):
    # ...
    role = config.get("default_role", "member")  # 问渠配置为 "student"
    user = User(
        phone=placeholder_phone,
        password_hash=password_hash,
        name=social_user.nickname or f"{PROVIDER_NAMES[provider]}用户",
        role=role,  # ← 从配置读
        status="active",
        tenant_id=config.get("default_tenant_id", 1),
    )
```

---

## 第三步：铁律

1. **next 参数必须校验**：只允许 `/` 开头的相对路径，禁止 `://` 协议，防止开放重定向漏洞
2. **问渠登录页样式必须和 cinnabar 主题一致**：`--cinnabar: #B03A2E`、`--paper: #F7F1E3`、`--font-kai: KaiTi`
3. **不改 DDW 主登录页 login.html**：它已经加了社会化按钮，不动
4. **不改 core/api/auth.py**：密码登录走底座，扫码登录走 ddw_social_login 插件
5. **state 缓存加 next 字段**：扫码授权是一次性跳转，state 里存 next 保证回调后跳对页面
6. **Pydantic 模型模块级定义**
7. **manifest.dependencies 必须是 dict**
8. **PluginBase.__init__ 自动调 self.setup()**

---

## 第四步：测试用例

| # | 测试 | 预期 |
|---|---|---|
| T1 | GET `/auth/wechat_open?next=/wenqu/student.html` | 302 → 微信授权页，state 缓存含 next |
| T2 | GET `/callback/wechat_open?code=test&state=valid`（state 缓存 next=/wenqu/student.html） | 302 → `/wenqu/student.html#access_token=xxx` |
| T3 | GET `/callback/wechat_open?code=test&state=valid&next=/evil.com` | 302 → `/pal.html`（next 被安全校验拦截，回退默认） |
| T4 | GET `/auth/wechat_open`（不传 next） | 302 → 微信授权页，state 缓存 next=/pal.html（默认） |
| T5 | 自动注册角色：`default_role=student` | User.role == "student" |
| T6 | 问渠登录页渲染：GET `/channels` → enabled=[wechat_open] → 页面显示"微信"按钮 |

---

## 第五步：验收命令

```bash
cd /Users/chenye/workspace/DDW底座平台/ddw-ai-hub
python -m pytest plugins/ddw_social_login/tests/ -v --tb=short
ruff check plugins/ddw_social_login/
grep -n "next\|wenqu\|student" plugins/ddw_social_login/router.py
grep -n "social\|微信\|wechat" frontend/wenqu/login.html
```
