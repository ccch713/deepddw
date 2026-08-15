你是 DDW AI Hub 的高级 Python 工程师。任务：开发 `ddw_social_login` 插件——微信/QQ/钉钉/飞书四种扫码登录通道。

严格按照下面的 TASK_SPEC 执行。所有代码写在 32G 本地仓库 `/Users/chenye/workspace/DDW底座平台/ddw-ai-hub/plugins/ddw_social_login/` 目录下。

---

# TASK_SPEC: ddw_social_login 插件

## 一、外部依赖

```bash
cd /Users/chenye/workspace/DDW底座平台/ddw-ai-hub
pip install senweaver-oauth>=0.1.4 cachetools>=5.0.0
```

`senweaver-oauth` 是 MIT License 的 Python OAuth 库，已内置微信/QQ/钉钉/飞书 40+ 平台的 OAuth2 授权流程。你不需要自己写 OAuth 跳转/换 token/拿用户信息，全部调库。

关键用法：
```python
from senweaver_oauth import AuthRequest, AuthConfig
from senweaver_oauth.source.wechat import AuthWechatSource
from senweaver_oauth.source.wechat_open import AuthWechatOpenSource
from senweaver_oauth.source.qq import AuthQqSource
from senweaver_oauth.source.dingtalk import AuthDingtalkSource
from senweaver_oauth.source.feishu import AuthFeishuSource

config = AuthConfig(
    client_id="your_appid",
    client_secret="your_secret",
    redirect_uri="https://your-domain.com/api/v1/plugins/ddw-social-login/callback/wechat_open"
)
auth_request = AuthRequest.build(AuthWechatOpenSource, config)
auth_url = auth_request.authorize("random-state-uuid")  # 返回授权页 URL
# 用户扫码后回调拿到 code + state
response = auth_request.login({"code": "授权码", "state": "random-state-uuid"})
# response.user.uuid = 平台唯一标识（openid/unionid）
# response.user.nickname = 昵称
# response.user.avatar = 头像
```

## 二、复用 core 已有能力（禁止重复实现）

以下函数/模型已经在 core 中，直接 import 使用：

### 2.1 签发 JWT
```python
from core.auth.jwt import create_access_token

token = create_access_token(
    user_id=user.id,           # int
    tenant_id=tenant.id,       # int
    role=user.role,            # str: "owner"/"admin"/"member"/"superadmin"/"partner"
)
```

### 2.2 写登录审计
```python
from core.api.auth import _write_login_audit

await _write_login_audit(
    phone=user.phone,          # str | None（扫码登录传 user.phone 或 None）
    ip=client_ip,              # str | None
    user_agent=ua,             # str | None
    method="social_wechat",    # str: "social_wechat"/"social_qq"/"social_dingtalk"/"social_feishu"
    success=True,              # bool
    fail_reason=None,          # str | None
)
```

### 2.3 已有数据模型（禁止新建表）
```python
# core/models.py 中已有：
from core.models import User, Tenant, UserBinding, LoginAudit

# UserBinding 字段：
# id, user_id(FK→users.id), tenant_id, provider(str 32),
# provider_uid(str 128), provider_name(str 128),
# binding_type(str 32, default="login"), is_primary(bool), is_active(bool)

# User 字段：
# id, phone(NOT NULL!), password_hash, name, role, status, tenant_id,
# device_required, device_allowlist, locked_until, email, email_verified
```

**注意**：`User.phone` 是 NOT NULL。扫码自动注册时需要生成占位手机号，格式：`"wx_{openid前16位}"` / `"qq_{openid前16位}"` / `"dt_{openid前16位}"` / `"fs_{openid前16位}"`。

### 2.4 数据库 session
```python
from core.database.session import session_scope

async with session_scope() as session:
    result = await session.execute(select(User).where(...))
    user = result.scalar_one_or_none()
```

### 2.5 多租户解析
扫码登录的多租户逻辑：
1. 通过 `UserBinding(provider, provider_uid)` 查找绑定记录 → 拿到 `user_id`
2. 通过 `user_id` 查 `User` 表 → 拿到 `tenant_id`
3. 如果有多条绑定记录（同 openid 绑了多个租户），用 `tenant_id` 参数区分；无参数时返回 409 `MULTI_TENANT`

### 2.6 设备校验（可选，P1）
```python
from core.auth.device_binding import check_device
# 如果 user.device_required=True，调此函数校验设备
```

## 三、目录结构

```
plugins/ddw_social_login/
├── manifest.yaml            # 插件声明 + 配置 schema
├── __init__.py              # from .plugin import Plugin
├── plugin.py                # PluginBase 子类，注册路由
├── router.py                # FastAPI APIRouter（全部端点）
├── schemas.py               # Pydantic 请求/响应模型（模块级定义，禁止闭包内定义！）
├── services.py              # OAuth 流程 + 账号解析/注册 + 绑定/解绑
├── config_manager.py        # 通道配置 CRUD（读写 manifest config）
├── frontend/
│   └── social_login_config.html  # 管理后台配置页
├── tests/
│   ├── conftest.py
│   ├── test_router.py       # API 端点测试
│   ├── test_services.py     # 服务层测试
│   └── test_csrf.py         # CSRF state 测试
└── README.md
```

## 四、manifest.yaml

```yaml
name: ddw-social-login
version: 1.0.0
display_name: DDW 社会化登录
description: 微信/QQ/钉钉/飞书扫码登录插件，基于 senweaver-oauth 统一 OAuth2 接口
engine: ">=2.0.0"
isolation: inline

permissions:
  - database.read
  - database.write

dependencies:
  plugins: {}

config_schema:
  type: object
  properties:
    enabled_channels:
      type: array
      default: []
      description: "启用的登录通道枚举: wechat_open / qq / dingtalk / feishu"
    auto_register:
      type: boolean
      default: true
      description: 首次扫码自动注册本地账号
    allowed_callback_domains:
      type: array
      default: ["ddw.9cio.com"]
      description: 回调 URL 白名单域名

router_prefix: /api/v1/plugins/ddw-social-login
```

## 五、Pydantic 模型（schemas.py，必须模块级定义）

```python
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ChannelConfig(BaseModel):
    """单个通道的配置"""
    provider: str = Field(..., description="通道标识: wechat_open / qq / dingtalk / feishu")
    enabled: bool = Field(False, description="是否启用")
    appid: Optional[str] = Field(None, description="第三方应用 AppID")
    app_secret: Optional[str] = Field(None, description="第三方应用 AppSecret")
    callback_url: Optional[str] = Field(None, description="回调 URL（可选，不填则自动生成）")


class ChannelConfigSave(BaseModel):
    """管理员保存通道配置"""
    channels: List[ChannelConfig]


class ChannelStatus(BaseModel):
    """通道状态（前端渲染按钮用）"""
    provider: str
    display_name: str  # "微信扫码" / "QQ 登录" / "钉钉登录" / "飞书登录"
    enabled: bool


class SocialBindRequest(BaseModel):
    """已登录用户绑定第三方账号"""
    provider: str
    code: str
    state: str


class SocialLoginCallbackResp(BaseModel):
    """扫码登录成功响应"""
    access_token: str
    token_type: str = "bearer"
    user: dict
    tenant: dict


class ErrorResponse(BaseModel):
    """统一错误响应"""
    code: str
    message: str
```

## 六、API 端点（router.py）

| 方法 | 路径 | 功能 | 请求 | 响应 |
|---|---|---|---|---|
| GET | `/auth/{provider}` | 生成授权 URL 并 302 跳转 | path: provider (wechat_open/qq/dingtalk/feishu) | 302 redirect → 第三方授权页 |
| GET | `/callback/{provider}` | 第三方回调 | query: code, state | 302 redirect → `/pal.html#token=xxx&user=xxx` |
| GET | `/channels` | 返回已启用通道列表 | 无 | `List[ChannelStatus]` |
| POST | `/config` | 管理员保存通道配置 | `ChannelConfigSave` | `{"ok": true}` |
| GET | `/config` | 管理员查看当前配置 | 无 | `List[ChannelConfig]`（secret 脱敏） |
| POST | `/bind/{provider}` | 已登录用户绑定第三方 | query: code, state（JWT 认证） | `{"ok": true, "provider": "xxx"}` |
| DELETE | `/bind/{provider}` | 已登录用户解绑 | path: provider（JWT 认证） | `{"ok": true}` |
| GET | `/bindings` | 查看当前用户的绑定列表 | JWT 认证 | `List[{provider, provider_name, bound_at}]` |

### 关键端点详细逻辑

#### GET `/auth/{provider}`
```
1. 校验 provider in ["wechat_open", "qq", "dingtalk", "feishu"]
2. 读取该通道的配置（appid/secret），未配置 → 400 CHANNEL_NOT_CONFIGURED
3. 生成 state = uuid4()
4. 存缓存：cache[state] = {"provider": provider, "created_at": now, "ttl": 300}
5. 构建回调 URL：f"{base_url}/api/v1/plugins/ddw-social-login/callback/{provider}"
6. auth_request = AuthRequest.build(PROVIDER_MAP[provider], config)
7. auth_url = auth_request.authorize(state)
8. 302 redirect → auth_url
```

#### GET `/callback/{provider}?code=xxx&state=yyy`
```
1. 校验 state 存在于缓存 → 不存在返回 401 INVALID_STATE
2. 删除缓存中的 state（一次性）
3. 校验回调域名在 allowed_callback_domains 白名单内
4. auth_request.login({"code": code, "state": state}) → 拿到用户信息
5. 查 UserBinding(provider=provider, provider_uid=response.user.uuid)
   - 找到 → user = User(binding.user_id)
   - 未找到 + auto_register=True → 创建 User + UserBinding
   - 未找到 + auto_register=False → 401 ACCOUNT_NOT_FOUND
6. 校验 user.status == "active"
7. create_access_token(user_id, tenant_id, role)
8. _write_login_audit(phone, ip, ua, f"social_{provider}", True)
9. redirect_uri = config 回调 URL 或默认 "/pal.html"
10. 302 redirect → f"{redirect_uri}#access_token={token}&user={json}"
```

#### 自动注册逻辑（services.py）
```python
async def auto_register_social_user(session, provider: str, social_user) -> User:
    """扫码首次登录自动注册"""
    # 生成占位手机号（User.phone 是 NOT NULL）
    placeholder_phone = f"{provider[:2]}_{social_user.uuid[:16]}"
    
    # 生成随机密码（用户后续可改）
    random_password = secrets.token_urlsafe(16)
    password_hash = hash_password(random_password)
    
    user = User(
        phone=placeholder_phone,
        password_hash=password_hash,
        name=social_user.nickname or f"{PROVIDER_NAMES[provider]}用户",
        role="member",
        status="active",
        tenant_id=DEFAULT_TENANT_ID,  # 从 config 读取默认租户
    )
    session.add(user)
    await session.flush()  # 拿到 user.id
    
    binding = UserBinding(
        user_id=user.id,
        tenant_id=user.tenant_id,
        provider=provider,
        provider_uid=social_user.uuid,
        provider_name=social_user.nickname,
        binding_type="login",
        is_primary=True,
        is_active=True,
    )
    session.add(binding)
    return user
```

## 七、通道配置管理（config_manager.py）

配置存储在插件 manifest.yaml 的 `config` 区域。运行时通过 `PluginBase.config` 读取。

```python
PROVIDER_DISPLAY_NAMES = {
    "wechat_open": "微信扫码",
    "qq": "QQ 登录",
    "dingtalk": "钉钉登录",
    "feishu": "飞书登录",
}

PROVIDER_MAP = {
    "wechat_open": AuthWechatOpenSource,
    "qq": AuthQqSource,
    "dingtalk": AuthDingtalkSource,
    "feishu": AuthFeishuSource,
}
```

配置通过 POST `/config` 保存，存入 manifest 的 `config.channels` 字段。读取时 secret 脱敏返回（只显示前4位 + `****`）。

## 八、前端改动

### 8.1 login.html 添加社会化登录按钮区

在现有登录表单的 `</form>` 之后，添加：
```html
<div id="social-login-section" style="display:none; margin-top: 24px;">
    <div style="text-align:center; color:#999; margin-bottom:16px;">
        <span style="background:#fff; padding:0 12px; position:relative; z-index:1;">其他登录方式</span>
        <hr style="margin-top:-10px; border:none; border-top:1px solid #eee;">
    </div>
    <div id="social-login-buttons" style="display:flex; justify-content:center; gap:16px; flex-wrap:wrap;">
        <!-- JS 动态渲染 -->
    </div>
</div>
<script>
(async function loadSocialButtons() {
    try {
        const resp = await fetch('/api/v1/plugins/ddw-social-login/channels');
        if (!resp.ok) return;
        const channels = await resp.json();
        const enabled = channels.filter(c => c.enabled);
        if (enabled.length === 0) return;
        document.getElementById('social-login-section').style.display = 'block';
        const container = document.getElementById('social-login-buttons');
        enabled.forEach(ch => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'ddw-btn ddw-btn-outline';
            btn.style.cssText = 'padding:8px 20px; border:1px solid #ddd; border-radius:6px; cursor:pointer; font-size:14px;';
            btn.textContent = ch.display_name;
            btn.onclick = () => location.href = `/api/v1/plugins/ddw-social-login/auth/${ch.provider}`;
            container.appendChild(btn);
        });
    } catch(e) { /* 插件未加载则静默 */ }
})();
</script>
```

### 8.2 social_login_config.html（管理后台配置页）

新建 `plugins/ddw_social_login/frontend/social_login_config.html`：
- 4 个通道卡片（微信/QQ/钉钉/飞书），每张卡片包含：启用开关、AppID 输入框、AppSecret 输入框、回调 URL 输入框、保存按钮
- 底部"测试连接"按钮（可选，P2）
- 复用 DDW admin.html 的侧栏和样式

## 九、测试用例（5-8 条）

| # | 测试 | 预期 |
|---|---|---|
| T1 | GET `/auth/dingtalk`（钉钉未配置） | 400 `CHANNEL_NOT_CONFIGURED` |
| T2 | POST `/config` 保存钉钉 appid/secret → GET `/auth/dingtalk` | 302 redirect 到 `oauth.dingtalk.com` |
| T3 | GET `/callback/dingtalk?code=test&state=invalid_state` | 401 `INVALID_STATE` |
| T4 | GET `/callback/dingtalk?code=test&state=valid_state`（state 有缓存，mock 模拟 senweaver 返回用户信息） | 200/302 + token + 自动注册 user + UserBinding 记录 |
| T5 | 同一 openid 第二次扫码登录 | 不重复创建 User，直接签发 token |
| T6 | POST `/config` 保存后 GET `/config` | 返回配置，secret 脱敏 |
| T7 | POST `/bind/wechat_open`（已登录用户绑定） | 200 + UserBinding 新增记录 |
| T8 | DELETE `/bind/wechat_open`（解绑） | 200 + UserBinding.is_active=False |

### pytest 运行命令
```bash
cd /Users/chenye/workspace/DDW底座平台/ddw-ai-hub
python -m pytest plugins/ddw_social_login/tests/ -v --tb=short
```

## 十、验收标准

| 标准 | 验证方式 |
|---|---|
| pytest 全部通过 | `pytest plugins/ddw_social_login/tests/ -v` 全绿 |
| 4 个通道均可 302 跳转 | 每个通道 GET `/auth/{provider}` 返回 302 |
| CSRF 防护生效 | 伪造 state 返回 401 |
| JWT 签发走 core | `grep -r "create_access_token" plugins/ddw_social_login/` 只调 core.auth.jwt |
| 审计写入 | `login_audit` 表有 `method LIKE 'social_%'` 记录 |
| 16G 无 Redis 可用 | 不 import redis，用 cachetools.TTLCache |
| ruff 通过 | `ruff check plugins/ddw_social_login/` 无错误 |
| Pydantic 模型模块级定义 | 所有 BaseModel 在函数/闭包外定义（FastAPI 422 坑） |

## 十一、Pitfalls（必须避免的坑）

1. **Pydantic 模型必须模块级定义**：`from __future__ import annotations` + 闭包内 `class XxxModel(BaseModel)` → FastAPI get_type_hints 解析失败 → 422 `Field required` on query。所有 BaseModel 写在 `schemas.py` 文件顶层。

2. **router prefix 必须带 `/api/v1`**：manifest 里已写 `router_prefix: /api/v1/plugins/ddw-social-login`，代码里 `APIRouter(prefix=...)` 要和 manifest 一致。

3. **UserBinding 已存在**：`core/models.py` 里已有 `UserBinding` 模型，禁止新建表。直接 import 使用。字段：`provider`/`provider_uid`/`provider_name`/`binding_type`/`is_primary`/`is_active`。

4. **User.phone 是 NOT NULL**：自动注册时必须给 phone 字段赋值，用占位格式 `"wx_{openid[:16]}"`。

5. **senweaver-oauth 的 authorize() 返回完整 URL 字符串**：不是 params dict。直接 302 redirect 到该 URL。

6. **回调处理是 GET 不是 POST**：微信/QQ/钉钉/飞书 OAuth 回调都是 GET 请求（浏览器跳转），不是 POST webhook。

7. **PluginBase.__init__ 自动调 self.setup()**：`setup()` 依赖的属性必须在 `super().__init__()` 之前初始化。

8. **manifest.dependencies 必须是 dict**：`plugins: {}`（不是 list），否则 manager.py 静默返回空。

9. **senweaver-oauth 依赖 requests（同步）**：在 async FastAPI 里调同步 requests 会阻塞事件循环。用 `asyncio.to_thread()` 包装或在 services.py 里用 `httpx` 替代。**优先用 asyncio.to_thread()，最小改动。**

10. **前端 JS 改完必须处理浏览器缓存**：login.html 的 JS 引用加 `?v=20260812` 版本号。
