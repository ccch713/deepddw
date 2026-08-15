# PRD：ddw-adapter-registry（IM 适配器统一注册表）v1.0.0

> 灵感来源：StaffDeck 的 channel-agnostic adapter registry + 意图自动路由（AGPL-3.0）
> 创建日期：2026-07-31
> 类型：🔧 重构增强（整合现有 ddw-adapter-dingtalk/feishu/wecom + ddw-smart-cs 路由逻辑）
> 许可证：Apache 2.0

---

## 零、问题定义

**现状**：DDW 有 3 个独立的 IM 适配器（ddw-adapter-dingtalk, ddw-adapter-feishu, ddw-adapter-wecom），各自有自己的消息接收/发送/鉴权逻辑，没有统一的注册表和路由层。ddw-smart-cs 客服插件需要自己判断"消息来自哪个渠道"。

**目标**：所有 IM 渠道通过统一注册表接入 → 统一消息格式 → 统一意图路由 → 统一发送。

---

## 一、核心设计：Adapter Registry

```python
# registry.py (伪代码)

class AdapterRegistry:
    """
    Channel Registry — 所有 IM 渠道适配器的统一注册表。
    新增渠道只需注册一个 Adapter 类，无需修改任何其他代码。
    """
    
    _adapters: dict[str, ChannelAdapter] = {}
    
    def register(self, channel_type: str, adapter: 'ChannelAdapter'):
        """注册渠道适配器"""
        self._adapters[channel_type] = adapter
    
    def get_adapter(self, channel_type: str) -> 'ChannelAdapter':
        """获取渠道适配器"""
        if channel_type not in self._adapters:
            raise ChannelNotSupportedError(f"Channel '{channel_type}' not registered")
        return self._adapters[channel_type]
    
    def list_channels(self) -> list[str]:
        return list(self._adapters.keys())


class ChannelAdapter(ABC):
    """
    渠道适配器抽象基类。
    每个 IM 渠道（企微/微信/飞书/钉钉）实现此接口。
    """
    
    channel_type: str  # "wecom" | "wechat" | "feishu" | "dingtalk"
    
    @abstractmethod
    async def receive_message(self, raw_payload: dict) -> ChannelMessage:
        """将渠道原始消息转换为统一的 ChannelMessage 格式"""
    
    @abstractmethod
    async def send_message(self, recipient: str, message: ChannelMessage) -> bool:
        """发送消息到渠道"""
    
    @abstractmethod
    async def validate_webhook(self, request: Request) -> bool:
        """验证 Webhook 请求合法性（签名校验等）"""
    
    @abstractmethod
    async def health_check(self) -> bool:
        """渠道连接健康检查"""


@dataclass
class ChannelMessage:
    """统一的消息格式——所有渠道消息转换为此格式"""
    message_id: str
    channel_type: str  # "wecom" | "wechat" | "feishu" | "dingtalk"
    sender_id: str
    sender_name: Optional[str]
    group_id: Optional[str]
    text: str
    attachments: list[dict] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    raw_payload: dict = field(default_factory=dict)  # 保留原始消息
    metadata: dict = field(default_factory=dict)
```

---

## 二、意图自动路由

```python
# router.py (伪代码)

class IntentRouter:
    """
    意图路由器。
    每条 IM 消息 → LLM 意图分类 → 路由到最匹配的"角色"（组合插件）。
    """
    
    async def route(self, message: ChannelMessage) -> RouteResult:
        """
        路由决策流程：
        1. 检查是否有"粘性"会话（用户手动 /切换 了角色）
        2. 检查是否在 SOP 执行中（此时不切换角色）
        3. LLM 意图分类 → 匹配最佳角色
        4. 返回路由结果
        """
        # Step 1: 检查粘性会话
        sticky_role = await self._get_sticky_role(message.sender_id)
        if sticky_role:
            return RouteResult(role=sticky_role, reason="sticky")
        
        # Step 2: 检查是否在 SOP 中
        active_sop = await self._get_active_sop(message.sender_id)
        if active_sop:
            return RouteResult(role=active_sop.bound_role, reason="sop_active")
        
        # Step 3: LLM 意图分类
        intent = await self._classify_intent(message.text)
        
        # Step 4: 匹配角色
        best_role = await self._match_role(intent)
        
        return RouteResult(role=best_role, intent=intent, reason="intent_match")


@dataclass
class RouteResult:
    role: 'PersonaRole'
    intent: Optional[dict]
    reason: str  # "sticky" | "sop_active" | "intent_match" | "default"
    confidence: float = 1.0
```

---

## 三、身份合并（Channel Identity → DDW Account）

```python
# identity.py

class IdentityManager:
    """
    渠道用户身份 ↔ DDW 账户映射。
    
    用法：
    - 用户在 IM 中发送 /绑定 <一次性验证码>
    - 系统将渠道用户 ID 与 DDW 账户绑定
    - 之后的会话/记忆统一归属到该账户
    """
    
    async def bind(self, channel_type: str, channel_user_id: str, 
                   ddw_account_id: str, one_time_code: str) -> bool:
        """绑定渠道身份到 DDW 账户"""
        # 验证一次性验证码
        code = await self._verify_otc(one_time_code, ddw_account_id)
        if not code:
            raise InvalidCodeError("验证码无效或已过期")
        
        # 创建绑定记录
        binding = ChannelBinding(
            channel_type=channel_type,
            channel_user_id=channel_user_id,
            ddw_account_id=ddw_account_id,
        )
        await self._save_binding(binding)
        return True
    
    async def unbind(self, channel_type: str, channel_user_id: str) -> bool:
        """解除绑定"""
    
    async def resolve(self, channel_type: str, channel_user_id: str) -> Optional[str]:
        """根据渠道用户 ID 查找 DDW 账户 ID"""
```

### 3.1 绑定流程

```
用户在企微发送："/绑定 ABC123"
       │
       ▼
IM 适配器识别命令 "/绑定"
       │
       ▼
IdentityManager.verify("ABC123")  ← 验证一次性验证码
       │
       ├─ 有效 → bind(channel_type="wecom", channel_user_id="user-xxx", ddw_account_id="...")
       │         回复："✅ 绑定成功！现在你可以使用 /切换 <角色名> 来切换数字员工。"
       │
       └─ 无效 → 回复："❌ 验证码无效或已过期，请重新生成。在 DDW 控制台 → 个人设置 → 渠道绑定中获取。"
```

---

## 四、Slash 命令系统

所有 IM 渠道支持统一的 Slash 命令（以 `/` 开头）：

| 命令 | 功能 | 示例 |
|:-----|:-----|:-----|
| `/帮助` | 显示所有可用命令 | `/帮助` |
| `/切换 <角色名>` | 切换到指定数字员工角色 | `/切换 客服助手` |
| `/当前` | 显示当前活跃的数字员工 | `/当前` |
| `/员工` | 列出所有可用数字员工 | `/员工` |
| `/绑定 <验证码>` | 绑定渠道身份到 DDW 账户 | `/绑定 ABC123` |
| `/解绑` | 解除绑定 | `/解绑` |
| `/状态` | 显示当前会话状态（SOP 进度等） | `/状态` |
| `/取消` | 取消当前正在执行的操作 | `/取消` |

---

## 五、消息可靠性保障

| 机制 | 实现 |
|:-----|:-----|
| **入站幂等** | 消息 ID 去重（Redis/DB），防止 Webhook 重复推送 |
| **出站重试** | 指数退避重试 3 次（1s/3s/9s） |
| **崩溃恢复** | Worker 进程重启后自动恢复未完成的出站消息 |
| **Token 过期告警** | 企微/微信 access_token 过期前 1 小时通过 DDW 通知告警 |
| **会话自愈** | 微信/企微 WebSocket 断线自动重连（退避：5s/15s/45s/135s） |

---

## 六、集成点

1. **现有适配器升级**：ddw-adapter-wecom/feishu/dingtalk 实现 `ChannelAdapter` 接口后自动注册
2. **ddw-smart-cs**：移除内置路由逻辑，改用 AdapterRegistry + IntentRouter
3. **ddw-sop-engine**：审批通知通过 AdapterRegistry 推送到指定渠道
4. **ddw-persona-engine**：角色绑定到渠道，实现"/切换"命令

---

## 七、配置

```yaml
name: ddw-adapter-registry
version: 1.0.0
description: "IM 适配器统一注册表"
author: DDW Team
license: Apache-2.0
engine: ">=2.0.0"
isolation: inline

permissions:
  - "api:ddw-smart-cs:read"
  - "network"

dependencies:
  plugins: {}
  python:
    - fastapi>=0.110
    - pydantic>=2.0

events:
  produces:
    - "channel.message.received"
    - "channel.message.sent"
  consumes:
    - "user.message.send"

config:
  optional:
    intent_classify_model: "mimo-v2.5-pro"
    sticky_session_ttl_minutes: 30

ecosystem:
  category: "infrastructure"
  tags: ["im", "adapter", "channel", "messaging"]
```

---



## X. 插件入口（DDW 规范要求）

### register(app) 注册函数

```python
# __init__.py
PLUGIN_NAME = "ddw-adapter-registry"
PLUGIN_VERSION = "1.0.0"

def register(app, config=None):
    """DDW 平台调用此函数挂载插件路由。"""
    from .router import router
    app.include_router(
        router,
        prefix=f"/api/v1/plugins/{PLUGIN_NAME}",
        tags=[PLUGIN_NAME],
    )
```

### 标准健康检查端点

```python
# router.py 中必须包含
@router.get("/health")
async def health():
    return {
        "plugin": PLUGIN_NAME,
        "status": "ok",
        "version": PLUGIN_VERSION,
        "endpoints": ["/channels", "/messages/send", "/identity/bind"],
    }
```

### 资源消耗声明（DDW 规范 §5.4）

| 维度 | 评估值 |
|:-----|:------|
| CPU 常态负载 | 5-10% |
| CPU 峰值负载 | 25% |
| 基础内存 | 64 MB |
| 运行时内存 | 128 MB |
| 峰值内存 | 256 MB |
| 代码体积 | 80 KB |
| 数据库存储 | 按使用量 |
| LLM Token | 走 DDW Gateway（不自配 Provider） |
| 必需依赖 | ddw-llm-gateway |
| 资源评级 | **轻量级/中等级** |

## 八、灵感溯源

- **灵感来源**：StaffDeck 的 channel-agnostic adapter registry + `/切换` 命令系统 + 身份绑定机制
- **DDW 实现**：全新 Apache 2.0。Adapter Registry 基于经典设计模式（GoF Strategy/Registry），IntentRouter 独立实现。Slash 命令解析器参考了 Discord/Slack Bot 命令范式

---

*本 PRD 为重构增强型需求。现有 3 个适配器需小幅修改以适配 ChannelAdapter 接口。*
