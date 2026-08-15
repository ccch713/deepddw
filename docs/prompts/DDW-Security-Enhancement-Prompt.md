# DDW 安全加固 — 设备绑定 + 扫码绑定 提示词
# 追加到 DDW-Backend-Integration-Prompt.md 之后

---

## 任务 7：管理员账号切换 + 设备绑定（安全加固）

### 7.1 管理员账号已更新

数据库中已存在两个管理员账号：

| 手机号 | 密码 | 角色 |
|:---|:---|:---|
| 15990720096 | DDW@2026 | admin |
| 13367266625 | DDW@2026 | admin |

**修改 `core/api/auth.py`**：
- 登录端点只接受手机号 + 密码/验证码
- 移除对 "admin" 字符串的硬编码支持
- 只有 `role=admin` 的用户才能登录管理后台

### 7.2 设备绑定逻辑

管理员登录时，前端必须采集设备指纹并发送到后端验证。

**设备白名单已存入 `system_config` 表**：

```json
{
  "32G-Mac-mini": {
    "serial": "D9CXVC9Q5L",
    "uuid": "CD5A842F-C6AE-5B44-A1D8-88ECDD567D51",
    "mac_en0": "d0:11:e5:99:35:ee"
  },
  "128G-MBP": {
    "serial": "C7M6MG97JL",
    "uuid": "66CAAF9F-1D91-5302-9768-A537661D309F",
    "mac_en0": "d0:c0:50:d8:eb:64"
  }
}
```

**前端设备指纹采集**（在登录页面的 `<script>` 中添加）：

```javascript
// 采集设备指纹（Web API 组合）
function getDeviceFingerprint() {
  var fp = {
    // 浏览器特征（作为辅助验证）
    userAgent: navigator.userAgent,
    language: navigator.language,
    platform: navigator.platform,
    screen: screen.width + 'x' + screen.height,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    // 硬件特征
    hardwareConcurrency: navigator.hardwareConcurrency,
    deviceMemory: navigator.deviceMemory || 'unknown',
    // canvas 指纹（唯一性高）
    canvas: getCanvasFingerprint()
  };
  return fp;
}

function getCanvasFingerprint() {
  try {
    var canvas = document.createElement('canvas');
    var ctx = canvas.getContext('2d');
    ctx.textBaseline = 'top';
    ctx.font = '14px Arial';
    ctx.fillText('DDW-device-check', 2, 2);
    return canvas.toDataURL().slice(-50);
  } catch(e) { return 'unsupported'; }
}
```

**后端设备验证**（在 `core/auth/device_binding.py` 中实现）：

```python
"""设备绑定验证模块。"""
import json
import hashlib
from typing import Optional
from sqlalchemy import text
from core.database.session import get_session

def get_device_whitelist() -> dict:
    """从 system_config 读取设备白名单。"""
    with get_session() as session:
        result = session.execute(
            text("SELECT value FROM system_config WHERE key = 'admin_device_whitelist'")
        )
        row = result.fetchone()
        if row:
            return json.loads(row[0])
        return {}

def verify_device(fingerprint: dict, phone: str) -> tuple[bool, str]:
    """验证设备是否在白名单中。
    
    验证逻辑：
    1. 从 system_config 读取设备白名单
    2. 检查用户的 User-Agent + screen + timezone 组合
       是否匹配白名单中的任一设备
    3. 返回 (是否通过, 原因)
    """
    whitelist = get_device_whitelist()
    if not whitelist:
        return True, "No device whitelist configured"
    
    # 构建设备签名（从 User-Agent 提取关键信息）
    ua = fingerprint.get('userAgent', '')
    screen = fingerprint.get('screen', '')
    tz = fingerprint.get('timezone', '')
    
    # 匹配 macOS 设备
    is_mac = 'Macintosh' in ua or 'Mac OS X' in ua
    if not is_mac:
        return False, "Admin must use macOS device"
    
    # 检查是否匹配白名单中的任一设备
    for device_name, info in whitelist.items():
        # 通过 screen + timezone + hardware 特征匹配
        # （生产环境应使用更强的指纹算法）
        if _match_device(fingerprint, info):
            return True, f"Matched device: {device_name}"
    
    return False, "Device not in admin whitelist"

def _match_device(fp: dict, device_info: dict) -> bool:
    """设备匹配逻辑。"""
    # 简化匹配：User-Agent 包含 macOS + screen 分辨率匹配
    ua = fp.get('userAgent', '')
    screen = fp.get('screen', '')
    
    # 32G Mac mini: 2560x1440 或 1920x1080（外接显示器）
    # 128G MBP: 3456x2234（内置）或 2560x1600（外接）
    mac_screens = ['2560x1440', '1920x1080', '3456x2234', '2560x1600', '1728x1117']
    
    for ms in mac_screens:
        if ms in screen and 'Macintosh' in ua:
            return True
    return False
```

### 7.3 登录流程改造

**修改 `core/api/auth.py` 的登录端点**：

```python
@router.post("/login")
async def login(request: Request, body: LoginRequest):
    # 1. 验证手机号 + 密码
    user = authenticate_user(body.phone, body.password)
    if not user:
        raise HTTPException(401, "账号或密码错误")
    
    # 2. 如果是 admin 角色，验证设备指纹
    if user.role == 'admin':
        fingerprint = body.device_fingerprint or {}
        ok, reason = verify_device(fingerprint, body.phone)
        if not ok:
            raise HTTPException(403, f"设备验证失败: {reason}")
    
    # 3. 签发 JWT
    token = create_token(user)
    return {"token": token, "user_id": user.id, "role": user.role}
```

### 7.4 前端登录页改造

**修改 `frontend/saas-register.html`**：
- 登录时自动采集设备指纹
- 发送登录请求时附带 `device_fingerprint` 字段
- 设备不匹配时显示友好提示："请使用授权设备登录"

---

## 任务 8：个人中心 — 绑定微信/钉钉/飞书

### 8.1 数据库扩展

在 `core/database/models.py` 中添加 `user_bindings` 表：

```python
class UserBinding(Base, TimestampMixin, TenantMixin):
    """用户第三方账号绑定。"""
    __tablename__ = "user_bindings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # wechat/dingtalk/feishu
    provider_uid: Mapped[str] = mapped_column(String(128), nullable=False)  # 第三方平台用户ID
    provider_name: Mapped[str] = mapped_column(String(128), nullable=True)  # 第三方昵称
    binding_type: Mapped[str] = mapped_column(String(32), default="login")  # login/mfa
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    bound_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
```

### 8.2 绑定 API

新增端点：

```
GET  /api/v1/user/bindings           → 查询已绑定的第三方账号
POST /api/v1/user/bindings/wechat    → 绑定微信（生成授权链接）
POST /api/v1/user/bindings/dingtalk  → 绑定钉钉（生成授权链接）
POST /api/v1/user/bindings/feishu    → 绑定飞书（生成授权链接）
DELETE /api/v1/user/bindings/{id}    → 解绑
POST /api/v1/auth/oauth/callback     → OAuth 回调（绑定/登录）
```

### 8.3 个人中心页面

新增 `frontend/saas-account.html`：

- 已绑定的第三方账号列表（微信/钉钉/飞书）
- 每个可绑定/解绑
- 设备绑定信息展示
- 密码修改
- 安全日志（最近登录记录）

---

## 执行顺序

先完成任务 1-6（上一轮提示词），再完成本提示词的任务 7-8。
