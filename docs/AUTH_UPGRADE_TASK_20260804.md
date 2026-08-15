# DDW 认证系统升级执行单（2026-08-04 凌晨）

> **执行人**：MiMo Code（32G设备）
> **前置条件**：用户已完成hCaptcha注册、飞书/钉钉开放平台申请

---

## 第一部分：准备工作（用户手动）

### 1.1 hCaptcha 注册（5分钟）

1. 打开 https://www.hcaptcha.com/
2. 点击 "Sign Up" → 选择 "I want to add hCaptcha to my website"
3. 填写：
   - Email: 你的邮箱
   - Password: 设置密码
   - Website URL: `https://ddw.9cio.com`（SaaS）或 `http://localhost:3000`（本地测试）
4. 验证邮箱后，进入 Dashboard
5. 复制 **Site Key** 和 **Secret Key**，保存到安全位置

**输出**：
- `HCAPTCHA_SITE_KEY`: 用于前端
- `HCAPTCHA_SECRET_KEY`: 用于后端

---

### 1.2 飞书开放平台申请（10分钟）

1. 打开 https://open.feishu.cn/
2. 登录飞书账号（没有就注册一个企业版，免费）
3. 创建应用：
   - 应用名称：DDW AI Hub
   - 应用描述：企业级AI能力平台
   - 应用类型：企业自建应用
4. 获取凭证：
   - App ID
   - App Secret
5. 配置重定向URL：
   - `https://ddw.9cio.com/api/v1/auth/feishu/callback`
   - `http://localhost:3000/api/v1/auth/feishu/callback`（本地测试）
6. 申请权限：
   - `contact:user.base:readonly`（获取用户基本信息）
   - `contact:user.employee_id:readonly`（获取员工ID）

**输出**：
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`

---

### 1.3 钉钉开放平台申请（10分钟）

1. 打开 https://open.dingtalk.com/
2. 登录钉钉账号（没有就注册一个企业版，免费）
3. 创建应用：
   - 应用名称：DDW AI Hub
   - 应用类型：企业内部应用
4. 获取凭证：
   - AppKey (Client ID)
   - AppSecret (Client Secret)
5. 配置登录回调URL：
   - `https://ddw.9cio.com/api/v1/auth/dingtalk/callback`
   - `http://localhost:3000/api/v1/auth/dingtalk/callback`
6. 申请权限：
   - `openid`（获取用户唯一标识）
   - `contact:user.base:readonly`（获取用户基本信息）

**输出**：
- `DINGTALK_APP_KEY`
- `DINGTALK_APP_SECRET`

---

## 第二部分：代码改动清单（MiMo Code 执行）

### 2.1 后端改动（FastAPI）

#### 文件：`core/config.py`
新增环境变量：
```python
# hCaptcha
hcaptcha_site_key: str = ""
hcaptcha_secret_key: str = ""

# 飞书
feishu_app_id: str = ""
feishu_app_secret: str = ""

# 钉钉
dingtalk_app_key: str = ""
dingtalk_app_secret: str = ""
```

#### 文件：`core/api/auth.py`

**改动1：新增 hCaptcha 验证函数**
```python
import httpx

async def verify_hcaptcha(token: str, remote_ip: str = None) -> bool:
    """验证 hCaptcha token，返回 True 表示通过"""
    from core.config import get_settings
    settings = get_settings()
    
    if not settings.hcaptcha_secret_key:
        # 未配置 hCaptcha 时直接放行（开发环境）
        return True
    
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://api.hcaptcha.com/siteverify", data={
            "secret": settings.hcaptcha_secret_key,
            "response": token,
            "remoteip": remote_ip
        })
        data = resp.json()
        return data.get("success", False)
```

**改动2：修改 RegisterReq 和 LoginReq**
```python
class RegisterReq(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)
    password: str = Field(..., min_length=6, max_length=128)  # 改为必填
    company_name: Optional[str] = Field(None, max_length=200)
    name: Optional[str] = Field(None, max_length=120)
    plan: str = Field("free", pattern="^(free|standard|enterprise)$")
    hcaptcha_token: Optional[str] = None  # 新增

class LoginPasswordReq(BaseModel):
    phone: str = Field(..., min_length=11, max_length=20)
    password: str = Field(..., min_length=6, max_length=128)
    device_fingerprint: Optional[Dict[str, Any]] = None
    hcaptcha_token: Optional[str] = None  # 新增
```

**改动3：修改 /register 端点**
```python
@router.post("/register", response_model=TokenResp, status_code=status.HTTP_201_CREATED)
async def register(req: RegisterReq, request: Request) -> TokenResp:
    """注册 → 创建 Tenant + 首位 owner User + 默认 TokenQuota → 签发 JWT"""
    
    # 验证 hCaptcha
    if req.hcaptcha_token:
        remote_ip = request.client.host if request.client else None
        if not await verify_hcaptcha(req.hcaptcha_token, remote_ip):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="人机验证失败，请刷新页面重试")
    
    # 删除验证码验证逻辑（不再需要）
    # 原来的 _consume_code 调用删除
    
    async with session_scope() as session, bypass_tenant_filter():
        existing = (await session.execute(select(User).where(User.phone == req.phone))).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该手机号已注册")
        
        company_name = (req.company_name or "").strip() or f"{req.phone} 的企业"
        tenant = await tenant_service.create_tenant(
            session, name=company_name, plan=req.plan, contact_phone=req.phone
        )
        user = User(
            tenant_id=tenant.id,
            phone=req.phone,
            password_hash=hash_password(req.password),  # 密码必填
            name=req.name or "管理员",
            role="owner",
            status="active",
        )
        session.add(user)
        try:
            await session.commit()
        except IntegrityError as e:
            await session.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"注册失败：{e.orig}") from e
        await session.refresh(user)
        
        token = create_access_token(user_id=user.id, tenant_id=tenant.id, role="owner")
        from core.config import get_settings
        
        return TokenResp(
            access_token=token,
            expires_in=get_settings().jwt_expires_minutes * 60,
            user={"id": user.id, "phone": user.phone, "name": user.name, "role": user.role},
            tenant={"id": tenant.id, "name": tenant.name, "plan": tenant.plan},
        )
```

**改动4：新增飞书 OAuth 端点**
```python
@router.get("/feishu/login")
async def feishu_login():
    """飞书扫码登录 - 跳转飞书授权页"""
    from core.config import get_settings
    settings = get_settings()
    
    redirect_uri = f"https://ddw.9cio.com/api/v1/auth/feishu/callback"
    auth_url = (
        f"https://open.feishu.cn/open-apis/authen/v1/authorize"
        f"?app_id={settings.feishu_app_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&state=ddw_feishu"  # 防CSRF
    )
    return RedirectResponse(url=auth_url)

@router.get("/feishu/callback")
async def feishu_callback(code: str, state: str = None):
    """飞书 OAuth 回调"""
    from core.config import get_settings
    settings = get_settings()
    
    async with httpx.AsyncClient() as client:
        # 1. 用 code 换取 user_access_token
        token_resp = await client.post(
            "https://open.feishu.cn/open-apis/authen/v1/oidc/access_token",
            headers={"Authorization": f"Bearer {await _get_tenant_access_token()}"},
            json={"grant_type": "authorization_code", "code": code}
        )
        token_data = token_resp.json()
        if token_data.get("code") != 0:
            raise HTTPException(status_code=400, detail="飞书授权失败")
        
        user_access_token = token_data["data"]["access_token"]
        
        # 2. 获取用户信息
        user_resp = await client.get(
            "https://open.feishu.cn/open-apis/authen/v1/user_info",
            headers={"Authorization": f"Bearer {user_access_token}"}
        )
        user_data = user_resp.json()["data"]
        
        feishu_user_id = user_data["user_id"]
        feishu_name = user_data.get("name", "飞书用户")
        feishu_avatar = user_data.get("avatar_url", "")
    
    # 3. 查找或创建用户
    async with session_scope() as session, bypass_tenant_filter():
        # 先通过飞书ID查找
        user = (await session.execute(
            select(User).where(User.feishu_user_id == feishu_user_id)
        )).scalar_one_or_none()
        
        if user is None:
            # 新用户：创建租户和用户
            tenant = await tenant_service.create_tenant(
                session, name=f"{feishu_name}的企业", plan="free"
            )
            user = User(
                tenant_id=tenant.id,
                feishu_user_id=feishu_user_id,
                name=feishu_name,
                avatar=feishu_avatar,
                role="owner",
                status="active",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        
        # 4. 签发 JWT
        token = create_access_token(user_id=user.id, tenant_id=user.tenant_id, role=user.role)
        
        # 5. 重定向到前端，携带 token
        frontend_url = f"https://ddw.9cio.com?token={token}&expires_in={settings.jwt_expires_minutes * 60}"
        return RedirectResponse(url=frontend_url)

async def _get_tenant_access_token() -> str:
    """获取飞书 tenant_access_token（用于调用API）"""
    from core.config import get_settings
    settings = get_settings()
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={
                "app_id": settings.feishu_app_id,
                "app_secret": settings.feishu_app_secret
            }
        )
        return resp.json()["tenant_access_token"]
```

**改动5：新增钉钉 OAuth 端点**
```python
@router.get("/dingtalk/login")
async def dingtalk_login():
    """钉钉扫码登录 - 跳转钉钉授权页"""
    from core.config import get_settings
    settings = get_settings()
    
    redirect_uri = f"https://ddw.9cio.com/api/v1/auth/dingtalk/callback"
    auth_url = (
        f"https://login.dingtalk.com/oauth2/auth"
        f"?client_id={settings.dingtalk_app_key}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=openid"
        f"&state=ddw_dingtalk"
        f"&prompt=consent"
    )
    return RedirectResponse(url=auth_url)

@router.get("/dingtalk/callback")
async def dingtalk_callback(code: str, state: str = None):
    """钉钉 OAuth 回调"""
    from core.config import get_settings
    settings = get_settings()
    
    async with httpx.AsyncClient() as client:
        # 1. 用 code 换取 user_access_token
        token_resp = await client.post(
            "https://api.dingtalk.com/v1.0/oauth2/userAccessToken",
            json={
                "clientId": settings.dingtalk_app_key,
                "clientSecret": settings.dingtalk_app_secret,
                "code": code,
                "grantType": "authorization_code"
            }
        )
        token_data = token_resp.json()
        if "accessToken" not in token_data:
            raise HTTPException(status_code=400, detail="钉钉授权失败")
        
        user_access_token = token_data["accessToken"]
        
        # 2. 获取用户信息
        user_resp = await client.get(
            "https://api.dingtalk.com/v1.0/contact/users/me",
            headers={"x-acs-dingtalk-access-token": user_access_token}
        )
        user_data = user_resp.json()
        
        dingtalk_user_id = user_data["openId"]
        dingtalk_name = user_data.get("name", "钉钉用户")
        dingtalk_avatar = user_data.get("avatarUrl", "")
    
    # 3. 查找或创建用户
    async with session_scope() as session, bypass_tenant_filter():
        user = (await session.execute(
            select(User).where(User.dingtalk_user_id == dingtalk_user_id)
        )).scalar_one_or_none()
        
        if user is None:
            tenant = await tenant_service.create_tenant(
                session, name=f"{dingtalk_name}的企业", plan="free"
            )
            user = User(
                tenant_id=tenant.id,
                dingtalk_user_id=dingtalk_user_id,
                name=dingtalk_name,
                avatar=dingtalk_avatar,
                role="owner",
                status="active",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        
        token = create_access_token(user_id=user.id, tenant_id=user.tenant_id, role=user.role)
        frontend_url = f"https://ddw.9cio.com?token={token}&expires_in={settings.jwt_expires_minutes * 60}"
        return RedirectResponse(url=frontend_url)
```

#### 文件：`core/database/models.py`

**User 模型新增字段**：
```python
class User(Base):
    # ... 现有字段 ...
    
    # OAuth 绑定字段
    feishu_user_id: Optional[str] = Column(String(64), unique=True, nullable=True, index=True)
    dingtalk_user_id: Optional[str] = Column(String(64), unique=True, nullable=True, index=True)
    wechat_openid: Optional[str] = Column(String(64), unique=True, nullable=True, index=True)  # 预留微信
    avatar: Optional[str] = Column(String(512), nullable=True)
```

#### 文件：`requirements.txt`

新增依赖：
```
httpx>=0.24.0
```

---

### 2.2 前端改动（HTML/JS）

#### 文件：`frontend/saas-register.html`

**改动1：引入 hCaptcha JS**
```html
<script src="https://js.hcaptcha.com/1/api.js" async defer></script>
```

**改动2：注册表单增加 hCaptcha 和密码确认**
```html
<!-- 在注册表单的提交按钮前增加 -->
<div class="form-group">
    <label>密码 <span class="required">*</span></label>
    <input class="form-input" type="password" id="regPassword" name="password" 
           placeholder="至少6位" minlength="6" required>
</div>
<div class="form-group">
    <label>确认密码 <span class="required">*</span></label>
    <input class="form-input" type="password" id="regPasswordConfirm" 
           placeholder="再次输入密码" minlength="6" required>
</div>
<div class="form-group">
    <div class="h-captcha" data-sitekey="YOUR_HCAPTCHA_SITE_KEY"></div>
</div>
```

**改动3：增加扫码登录入口**
```html
<!-- 在登录/注册 Tab 下方增加 -->
<div class="oauth-divider">
    <span>或使用以下方式登录</span>
</div>
<div class="oauth-buttons">
    <button class="oauth-btn feishu" onclick="location.href='/api/v1/auth/feishu/login'">
        <img src="https://lf-cdn.feishu.cn/obj/icon-lark/open-platform/icon_feishu.svg" alt="飞书">
        飞书扫码登录
    </button>
    <button class="oauth-btn dingtalk" onclick="location.href='/api/v1/auth/dingtalk/login'">
        <img src="https://img.alicdn.com/tfs/TB1p4J5cW61gK0jSZFlXXXDKFXa-200-200.png" alt="钉钉">
        钉钉扫码登录
    </button>
</div>
```

**改动4：CSS 样式**
```css
.oauth-divider {
    display: flex;
    align-items: center;
    margin: 20px 0;
    color: #999;
}
.oauth-divider::before,
.oauth-divider::after {
    content: '';
    flex: 1;
    height: 1px;
    background: #eee;
}
.oauth-divider span {
    padding: 0 12px;
    font-size: 12px;
}
.oauth-buttons {
    display: flex;
    gap: 12px;
}
.oauth-btn {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 12px;
    border: 1px solid #ddd;
    border-radius: 6px;
    background: white;
    cursor: pointer;
    transition: all 0.2s;
}
.oauth-btn:hover {
    border-color: #333;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}
.oauth-btn img {
    width: 20px;
    height: 20px;
}
.oauth-btn.feishu:hover {
    border-color: #3370ff;
    color: #3370ff;
}
.oauth-btn.dingtalk:hover {
    border-color: #0089ff;
    color: #0089ff;
}
```

**改动5：JS 注册逻辑修改**
```javascript
// 注册表单提交
$('#regForm').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    
    const phone = $('#regPhone').value.trim();
    const password = $('#regPassword').value;
    const passwordConfirm = $('#regPasswordConfirm').value;
    const company_name = $('#regCompany').value.trim();
    const name = $('#regName').value.trim();
    
    // 密码校验
    if (password !== passwordConfirm) {
        alert('两次密码不一致');
        return;
    }
    
    // 获取 hCaptcha token
    const hcaptchaResponse = hcaptcha.getResponse();
    if (!hcaptchaResponse) {
        alert('请完成人机验证');
        return;
    }
    
    try {
        const r = await fetch(API_BASE + '/api/v1/auth/register', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                phone,
                password,
                company_name,
                name,
                plan: 'free',
                hcaptcha_token: hcaptchaResponse
            })
        });
        
        const data = await r.json();
        
        if (r.ok) {
            // 保存 token
            localStorage.setItem('ddw_token', data.access_token);
            localStorage.setItem('ddw_user', JSON.stringify(data.user));
            localStorage.setItem('ddw_tenant', JSON.stringify(data.tenant));
            
            alert('注册成功！');
            location.href = '/dashboard.html';
        } else {
            alert(data.detail || '注册失败');
        }
    } catch (err) {
        alert('网络错误');
    }
});
```

**改动6：页面加载时检查 URL 参数（OAuth 回调）**
```javascript
// 页面加载时检查是否从 OAuth 回调
window.addEventListener('DOMContentLoaded', () => {
    const params = new URLSearchParams(location.search);
    const token = params.get('token');
    const expiresIn = params.get('expires_in');
    
    if (token) {
        // 保存 token
        localStorage.setItem('ddw_token', token);
        
        // 清除 URL 参数
        history.replaceState({}, '', location.pathname);
        
        // 跳转到 dashboard
        location.href = '/dashboard.html';
    }
});
```

---

### 2.3 数据库迁移

#### 文件：`alembic/versions/xxxx_add_oauth_fields.py`

```python
"""add OAuth fields to users table

Revision ID: xxxx
Revises: <previous_revision>
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('users', sa.Column('feishu_user_id', sa.String(64), nullable=True))
    op.add_column('users', sa.Column('dingtalk_user_id', sa.String(64), nullable=True))
    op.add_column('users', sa.Column('wechat_openid', sa.String(64), nullable=True))
    op.add_column('users', sa.Column('avatar', sa.String(512), nullable=True))
    
    op.create_index('ix_users_feishu_user_id', 'users', ['feishu_user_id'], unique=True)
    op.create_index('ix_users_dingtalk_user_id', 'users', ['dingtalk_user_id'], unique=True)
    op.create_index('ix_users_wechat_openid', 'users', ['wechat_openid'], unique=True)

def downgrade():
    op.drop_index('ix_users_wechat_openid')
    op.drop_index('ix_users_dingtalk_user_id')
    op.drop_index('ix_users_feishu_user_id')
    op.drop_column('users', 'avatar')
    op.drop_column('users', 'wechat_openid')
    op.drop_column('users', 'dingtalk_user_id')
    op.drop_column('users', 'feishu_user_id')
```

---

## 第三部分：测试清单

### 3.1 功能测试

- [ ] hCaptcha 注册：填完表单 → 点击验证 → 提交 → 注册成功
- [ ] 密码登录：手机号 + 密码 → 登录成功
- [ ] 飞书扫码：点击飞书按钮 → 跳转飞书授权页 → 扫码 → 回调 → 登录成功
- [ ] 钉钉扫码：点击钉钉按钮 → 跳转钉钉授权页 → 扫码 → 回调 → 登录成功
- [ ] 重复注册：已注册手机号 → 提示"该手机号已注册"
- [ ] 密码强度：少于6位 → 提示错误

### 3.2 安全测试

- [ ] hCaptcha 绕过：直接调 API 不带 token → 返回"人机验证失败"
- [ ] CSRF 防护：OAuth state 参数验证
- [ ] Token 泄露：URL 中 token 参数在页面加载后清除

### 3.3 边界测试

- [ ] hCaptcha 未配置：开发环境不填 key → 直接放行
- [ ] 飞书/钉钉未配置：点击按钮 → 提示"暂未开放"
- [ ] 网络超时：飞书/钉钉 API 超时 → 提示"登录超时，请重试"

---

## 第四部分：部署检查清单

- [ ] 环境变量配置：`.env` 文件添加所有 key
- [ ] 数据库迁移：`alembic upgrade head`
- [ ] 前端缓存：清除 CDN 缓存（如果有）
- [ ] CORS 配置：确保飞书/钉钉回调域名在白名单
- [ ] 日志监控：观察 `/api/v1/auth/feishu/callback` 和 `/api/v1/auth/dingtalk/callback` 的错误日志

---

## 第五部分：常见问题

### Q1: hCaptcha 加载慢怎么办？
A: 使用 hCaptcha 的 `enterprise` 版本（付费），或者改用国内的极验（Geetest）。

### Q2: 飞书/钉钉扫码后提示"该手机号已注册"？
A: 需要实现"账号绑定"功能：已注册用户可以在个人中心绑定飞书/钉钉账号。这是第二阶段功能。

### Q3: 本地开发怎么测试 OAuth？
A: 使用 ngrok 或者 frp 把本地服务暴露到公网，然后在飞书/钉钉配置回调 URL。

### Q4: 微信开放平台申请需要什么？
A: 企业营业执照 + 已备案域名。个人无法申请。

---

**执行完成标志**：所有测试清单通过 + ECS 部署成功 + 客户可以正常注册登录

---

## 附录：文件改动总览

| 文件 | 改动类型 | 改动内容 |
|:-----|:---------|:---------|
| `core/config.py` | 新增 | 6个环境变量（hCaptcha/飞书/钉钉） |
| `core/api/auth.py` | 重构 | 删除短信逻辑，新增 hCaptcha 验证 + 飞书/钉钉 OAuth |
| `core/database/models.py` | 新增 | User 模型增加 4 个字段 |
| `alembic/versions/xxxx_add_oauth_fields.py` | 新增 | 数据库迁移脚本 |
| `requirements.txt` | 新增 | httpx 依赖 |
| `frontend/saas-register.html` | 重构 | 新增 hCaptcha + OAuth 按钮 + 样式 |
