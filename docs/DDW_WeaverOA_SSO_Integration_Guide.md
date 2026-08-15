# DDW AI Hub 集成泛微OA 统一认证中心 — 部署配置指南

> 版本：v1.0 · 2026-08-05
> 适用：DDW AI Hub v5.5+ · 泛微OA E9/E10（100统一认证中心非标）

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────┐
│                    泛微OA系统                         │
│  ┌─────────────────────────────────────────────┐    │
│  │         统一认证中心（100非标）                │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │    │
│  │  │ CAS认证  │  │ OAuth2   │  │ SPNEGO   │  │    │
│  │  └────┬─────┘  └────┬─────┘  └──────────┘  │    │
│  │       │              │                       │    │
│  │  ┌────┴──────────────┴──────────────────┐   │    │
│  │  │       认证应用管理                     │   │    │
│  │  │  ┌─────────────────────────────────┐ │   │    │
│  │  │  │ DDW AI Hub (appid=ddw_hub)      │ │   │    │
│  │  │  │ 认证方式: CAS/OAuth2            │ │   │    │
│  │  │  │ 业务系统URL: https://ddw.xxx    │ │   │    │
│  │  │  │ 账号映射: 登录名                │ │   │    │
│  │  │  └─────────────────────────────────┘ │   │    │
│  │  └──────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────┘    │
│                       │                              │
│         ┌─────────────┼──────────────┐              │
│         │ 302重定向    │ ticket验证     │              │
│         ▼             ▼              │              │
│  ┌──────────────────────────────────┐│              │
│  │         DDW AI Hub               ││              │
│  │  ┌────────────────────────────┐  ││              │
│  │  │ core/auth/weaver_sso.py   │◄─┘│              │
│  │  │ core/api/sso.py           │   │              │
│  │  └────────────────────────────┘  │              │
│  │  ┌────────────────────────────┐  │              │
│  │  │ 前端页面                    │  │              │
│  │  │ oa-homepage.html          │  │              │
│  │  │ oa-quality.html           │  │              │
│  │  └────────────────────────────┘  │              │
│  └──────────────────────────────────┘              │
└─────────────────────────────────────────────────────┘
```

## 2. 泛微OA端配置

### 2.1 申请非标功能

| 认证方式 | 非标编号 | 版本要求 |
|---------|---------|---------|
| CAS | 090 CAS集成 | 标准功能 |
| OAuth2 | 128 OAuth2集成 | KB9001912**以后 |
| 统一认证中心 | 100 | KB900200300以后 |

### 2.2 在认证应用管理中注册DDW

1. 登录OA管理后台
2. 进入【集成中心】→【统一认证中心】→【认证服务管理】→【认证应用管理】
3. 点击【注册】，填写：

| 字段 | 值 |
|-----|---|
| 启用 | 开启 |
| 认证方式 | CAS 或 OAUTH2 |
| 应用标识 | `ddw_hub`（点击生成按钮自动生成） |
| 应用密钥 | OAuth2方式需要（点击生成） |
| 应用简称 | DDW AI Hub |
| 应用全称 | DDW AI Hub 企业数字化底座平台 |
| 链接图标 | 上传DDW Logo |
| IP白名单 | DDW服务器IP（如 192.168.1.8） |
| 业务系统URL | `https://ddw.example.com`（OAuth2回调地址） |
| 账号映射规则 | 登录名 |

### 2.3 配置授权设置（可选）

如需限制哪些OA用户可以访问DDW，在编辑应用中配置授权设置。

### 2.4 OA门户嵌入（统一认证中心元素）

1. 进入OA门户管理
2. 添加"统一认证中心"元素
3. 配置显示DDW应用图标
4. 用户点击即可免登录跳转到DDW

## 3. DDW端配置

### 3.1 deployment.yaml 配置

在 `config/deployment.yaml` 中添加：

```yaml
weaver_sso:
  enabled: true
  active_protocol: cas          # cas 或 oauth2
  auto_register: true           # OA用户首次SSO登录自动创建DDW账号
  default_tenant_id: 1          # SSO自动注册用户的默认租户ID
  embed_shared_secret: ""       # OA嵌入iframe模式的共享密钥（可选）

  cas:
    enabled: true
    oa_url: "http://192.168.1.100:8080"   # 泛微OA访问地址
    appid: "ddw_hub"                       # OA认证应用管理中的应用标识
    callback_url: "https://ddw.example.com/api/v1/sso/cas/callback"

  oauth2:
    enabled: false
    oa_url: "http://192.168.1.100:8080"
    client_id: ""                # OA认证应用管理中的应用标识
    client_secret: ""            # OA认证应用管理中的应用密钥
    callback_url: "https://ddw.example.com/api/v1/sso/oauth2/callback"
```

### 3.2 环境变量

```bash
# 可选：OA域名加入CORS白名单
export DDW_WEAVER_OA_URL="http://192.168.1.100:8080"
```

### 3.3 Nginx/Caddy 反向代理配置

确保SSO回调URL能正确到达DDW后端：

```caddyfile
ddw.example.com {
    reverse_proxy localhost:8500
}
```

## 4. DDW前端页面嵌入OA

### 4.1 方式一：OA门户统一认证中心元素（推荐）

在OA门户中添加"统一认证中心"元素，DDW应用注册后自动显示。
用户点击DDW图标 → 自动跳转到DDW（已登录状态）。

### 4.2 方式二：iframe嵌入

在OA自定义页面中嵌入DDW页面：

```html
<!-- OA自定义HTML页面 -->
<iframe
  src="https://ddw.example.com/oa-quality.html?embed=1"
  width="100%"
  height="800"
  frameborder="0"
  style="border: 1px solid #e0e0e0; border-radius: 8px;"
></iframe>
```

### 4.3 方式三：OA菜单链接

在OA菜单管理中添加外部链接：
- 菜单名称：DDW质量管理
- 链接地址：`https://ddw.example.com/oa-quality.html`
- 打开方式：新窗口

## 5. 质量管理插件群OA集成页面

| 页面 | 路径 | 功能 |
|-----|------|------|
| DDW首页(OA版) | `/oa-homepage.html` | OA集成首页，显示所有功能入口 |
| 质量管理(OA版) | `/oa-quality.html` | 8D/CAPA/偏差/投诉/5Why一站式 |

这些页面特性：
- 自动检测SSO token，未登录自动跳转OA登录
- 支持iframe嵌入（`?embed=1`参数）
- 响应式布局，适配OA门户
- 调用质量管理插件API，需要用户已有DDW JWT

## 6. 账号映射规则

| OA字段 | DDW字段 | 映射规则 |
|--------|---------|---------|
| 登录名(loginid) | phone | `oa_{loginid}`（如 `oa_zhangsan`） |
| 姓名(lastname) | name | 直接映射 |
| 邮箱(email) | - | 暂不映射（User模型无email字段） |

首次SSO登录时自动创建DDW账号（`auto_register: true`）。

## 7. 安全注意事项

1. **IP白名单**：OA认证应用管理中必须配置DDW服务器IP
2. **HTTPS**：生产环境SSO回调必须使用HTTPS
3. **CORS**：OA域名已加入DDW CORS白名单
4. **token传输**：SSO回调使用URL hash传递JWT，不会出现在服务器日志
5. **embed模式**：iframe嵌入使用HMAC-SHA256签名防伪造

## 8. 故障排查

| 问题 | 排查方向 |
|------|---------|
| CAS ticket验证失败 | 检查OA访问地址连通性：`curl 'OA_URL/sso/login?appid=xxx&service=xxx'` |
| OAuth2 code换取失败 | 检查client_id/client_secret是否正确 |
| 用户自动注册失败 | 检查default_tenant_id对应的租户是否存在 |
| iframe嵌入后登录循环 | 检查浏览器第三方Cookie策略，建议用新窗口方式 |
| OA地址变更后SSO失效 | OA系统设置中更新访问地址 + CAS/OAuth2页面重新保存 |
