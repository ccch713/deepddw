# DDW 社会化登录插件

微信/QQ/钉钉/飞书扫码登录插件，基于 [senweaver-oauth](https://pypi.org/project/senweaver-oauth/) 统一 OAuth2 接口。

## 功能

- **扫码登录**：支持微信开放平台、QQ 互联、钉钉、飞书四种扫码登录通道
- **自动注册**：首次扫码可自动创建本地账号（可配置关闭）
- **绑定/解绑**：已登录用户可绑定/解绑第三方账号
- **多租户**：通过 UserBinding 记录自动解析租户
- **CSRF 防护**：state 参数一次性校验，防伪造回调
- **配置管理**：管理后台可视化配置各通道 AppID/Secret

## API 端点

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/auth/{provider}` | 生成授权 URL 并 302 跳转 |
| GET | `/callback/{provider}` | 第三方 OAuth 回调 |
| GET | `/channels` | 返回已启用通道列表 |
| POST | `/config` | 管理员保存通道配置 |
| GET | `/config` | 管理员查看当前配置（secret 脱敏） |
| POST | `/bind/{provider}` | 已登录用户绑定第三方 |
| DELETE | `/bind/{provider}` | 已登录用户解绑 |
| GET | `/bindings` | 查看当前用户的绑定列表 |

## 依赖

- `senweaver-oauth>=0.1.4` — OAuth2 授权流程
- `cachetools>=5.0.0` — TTL 缓存（替代 Redis，适配 16G 内存场景）

## 配置

在插件 manifest.yaml 或 deployment.yaml 中配置：

```yaml
config:
  auto_register: true
  default_tenant_id: 1
  allowed_callback_domains: ["ddw.9cio.com"]
  channels:
    wechat_open:
      enabled: true
      appid: "wx..."
      app_secret: "..."
    dingtalk:
      enabled: true
      appid: "ding..."
      app_secret: "..."
```

## 测试

```bash
python -m pytest plugins/ddw_social_login/tests/ -v --tb=short
```
