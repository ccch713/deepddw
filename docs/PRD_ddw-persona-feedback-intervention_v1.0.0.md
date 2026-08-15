# PRD：ddw-persona-engine + ddw-feedback-loop + Intervention Hooks（合并）v1.0.0

> 灵感来源：StaffDeck 的"数字员工角色系统 + 人工接管 + 反馈闭环"（AGPL-3.0）
> 创建日期：2026-07-31
> 类型：🆕 新建（persona-engine, feedback-loop）+ 🔧 SDK 增强（intervention_hooks）
> 许可证：Apache 2.0

---

# Part A：ddw-persona-engine（数字员工角色系统）

## A.1 一句话定位

**ddw-persona-engine** 将多个 DDW 插件的组合封装为"角色" —— 一键部署的、有身份的、可切换的数字员工。

## A.2 核心概念

```
角色 (PersonaRole) = 多个插件的组合 + 身份定义

示例：客服角色 = {
    "name": "客服助手",
    "description": "7×24小时智能客服，处理售前咨询和售后投诉",
    "plugins": ["ddw-smart-cs", "ddw-knowledge-hierarchy", "ddw-adapter-wecom"],
    "system_prompt": "你是DDW公司的客服助手...",
    "allowed_tools": ["search_knowledge", "create_ticket", "send_email"],
    "response_style": "友好、专业、简洁",
    "escalation_role": "人工客服（当置信度 < 0.7 时转接）"
}
```

## A.3 数据模型

```python
class PersonaRole(Base):
    __tablename__ = 'persona_roles'

    id = Column(String(36), primary_key=True)
    name = Column(String(128), nullable=False, unique=True)
    display_name = Column(String(256), nullable=False)
    description = Column(Text)
    avatar_url = Column(String(1024))
    
    # 角色配置
    system_prompt = Column(Text, nullable=False)
    response_style = Column(String(64), default='professional')
    # friendly | professional | concise | detailed
    
    # 插件组合
    plugins = Column(JSON, nullable=False)
    # ["ddw-smart-cs@1.0.0", "ddw-knowledge-hierarchy@1.0.0"]
    
    # 工具白名单
    allowed_tools = Column(JSON)
    # ["search_knowledge", "create_ticket", "send_email"]
    
    # 知识桶
    knowledge_buckets = Column(JSON)
    # ["product_manual", "faq", "refund_policy"]
    
    # SOP 绑定
    bound_sops = Column(JSON)
    # [{"sop_id": "xxx", "trigger": "on_complaint", "auto_execute": true}]
    
    # 升级策略
    escalation_role_id = Column(String(36), ForeignKey('persona_roles.id'))
    escalation_threshold = Column(Float, default=0.7)  # 置信度低于此值时转接
    escalation_timeout_minutes = Column(Integer, default=5)
    
    # 权限
    access_level = Column(String(32), default='internal')
    is_public = Column(Boolean, default=False)  # 是否在市场公开
    
    # 发布者
    publisher_id = Column(String(36))
    version = Column(String(16), default='1.0.0')
    
    created_at = Column(DateTime, default=datetime.utcnow)
```

## A.4 API 端点

```python
router = APIRouter(prefix="/api/persona", tags=["Persona Engine"])

# CRUD
POST   /roles              # 创建角色
GET    /roles              # 列出角色（含市场公开角色）
GET    /roles/{role_id}    # 获取角色详情 + 依赖插件清单
PUT    /roles/{role_id}    # 更新角色
DELETE /roles/{role_id}    # 删除角色

# 一键部署
POST   /roles/{role_id}/deploy    # 一键安装角色的所有依赖插件
GET    /roles/{role_id}/status    # 检查角色的依赖插件是否齐全

# 切换
POST   /roles/switch              # 在 IM 中切换活跃角色
GET    /roles/active              # 获取当前活跃角色

# 市场
POST   /roles/{role_id}/publish   # 发布角色到市场
POST   /roles/{role_id}/fork      # Fork 一个角色（创建本地副本）
```

## A.5 一键部署流程

```
用户在 DDW 控制台 → 角色市场 → 点击"安装客服角色"
    │
    ▼
PersonaEngine.deploy("客服助手")
    │
    ├─ 检查依赖：smart-cs ✓ installed / knowledge-hierarchy ✗ missing / adapter-wecom ✗ missing
    │
    ├─ 自动安装缺失插件（从 DDW Plugin Marketplace 下载）
    │
    ├─ 配置插件（注入 system_prompt + knowledge_buckets + allowed_tools）
    │
    ├─ 绑定 IM 渠道到角色
    │
    └─ 完成！用户在企微中发送 /切换 客服助手 即可使用
```

---

# Part B：ddw-feedback-loop（反馈收集与持续改进）

## B.1 一句话定位

**ddw-feedback-loop** 收集用户对 AI 回答的反馈，通过 LLM 分析转化为具体的改进建议，形成持续优化闭环。

## B.2 数据模型

```python
class UserFeedback(Base):
    __tablename__ = 'user_feedback'

    id = Column(String(36), primary_key=True)
    conversation_id = Column(String(36), index=True)
    trace_id = Column(String(36), index=True)
    
    # 反馈
    rating = Column(Integer)  # 1-5
    feedback_text = Column(Text, nullable=True)
    feedback_type = Column(String(32))  # accuracy | tone | completeness | speed | other
    
    # 上下文快照
    question_snapshot = Column(Text)
    answer_snapshot = Column(Text)
    sources_snapshot = Column(JSON)
    
    # AI 分析结果
    analysis = Column(JSON, nullable=True)
    """
    {
        "root_cause": "knowledge_gap",  // knowledge_gap | prompt_issue | model_hallucination | tool_error
        "improvement_suggestion": "《退款政策》文档缺少'跨境退款'的相关规定，建议补充",
        "auto_fix_possible": true,
        "auto_fix_action": "add_knowledge",
        "affected_documents": ["refund_policy_v2.pdf"],
        "suggested_content": "..."
    }
    """
    
    # 处理状态
    analysis_status = Column(String(32), default='pending')
    # pending | analyzed | fix_applied | fix_verified | dismissed
    
    created_at = Column(DateTime, default=datetime.utcnow)
    analyzed_at = Column(DateTime)
    fix_applied_at = Column(DateTime)
```

## B.3 API 端点

```python
router = APIRouter(prefix="/api/feedback", tags=["Feedback Loop"])

POST   /feedback          # 提交反馈（用户在 IM/Web 中 👍/👎）
GET    /feedback          # 列出反馈（按时间/评分/类型筛选）
POST   /feedback/{id}/analyze    # 触发 LLM 分析反馈
POST   /feedback/{id}/dismiss    # 忽略反馈
GET    /feedback/stats           # 反馈统计（满意度趋势/常见问题）
GET    /feedback/suggestions     # 改进建议列表（已分析但未应用的）
POST   /feedback/{id}/apply-fix  # 应用自动修复（如补充知识库）
```

## B.4 反馈闭环流程

```
用户发送 👍 或 👎
       │
       ▼
UserFeedback 记录 (rating + text)
       │
       ▼
LLM 分析 (每 10 条新反馈批量分析，降低成本)
       │
       ├─ knowledge_gap → 建议补充知识库文档
       ├─ prompt_issue → 建议修改 system_prompt
       ├─ model_hallucination → 建议增加 guard / post-condition
       └─ tool_error → 建议修复插件 Tool
       │
       ▼
自动修复（可选）
  - knowledge_gap → 自动生成补充文档草稿 → 人工审核 → 入库
  - prompt_issue → 自动生成改进版 prompt → 人工审核 → A/B Test
       │
       ▼
人工审核 → 应用修复 → 标记 fix_applied
       │
       ▼
验证修复效果（后续 7 天的同类型反馈率是否下降）
```

---

# Part C：Intervention Hooks（SDK 增强）

## C.1 PluginBase v2 新增接口

```python
# sdk/plugin_base.py (增量)

class InterventionHooks:
    """
    干预钩子——允许人工接管 AI 的决策和执行。
    所有钩子都是可选的，插件按需实现。
    """
    
    async def on_uncertain(self, context: dict) -> InterventionAction:
        """
        当 AI 置信度低于阈值时触发。
        默认行为：自动降级到人工。
        
        插件可覆盖此方法实现自定义逻辑：
        - 特定场景下强制执行（如涉及金额 > 1000 元的退款）
        - 特定场景下跳过（如简单的 FAQ 查询）
        """
        return InterventionAction.ESCALATE_TO_HUMAN
    
    async def on_before_tool_call(self, tool_name: str, params: dict) -> InterventionAction:
        """
        在 Tool 调用前触发。
        用于高风险操作的拦截——如删除数据、发送外部请求。
        """
        HIGH_RISK_TOOLS = {'delete_record', 'send_external_request', 'modify_database'}
        if tool_name in HIGH_RISK_TOOLS:
            return InterventionAction.REQUIRE_APPROVAL
        return InterventionAction.ALLOW
    
    async def on_user_feedback(self, feedback: UserFeedback) -> None:
        """
        收到用户反馈时触发。
        插件可覆盖以实现自定义处理（如记录到外部系统）。
        """
        pass
    
    async def on_sop_pause(self, instance_id: str, reason: str) -> None:
        """SOP 实例暂停时触发"""
        pass
    
    async def on_sop_resume(self, instance_id: str) -> None:
        """SOP 实例恢复时触发"""
        pass


class InterventionAction(str, enum.Enum):
    ALLOW = "allow"                      # 允许继续
    ESCALATE_TO_HUMAN = "escalate"       # 转接人工
    REQUIRE_APPROVAL = "require_approval" # 需要审批
    PAUSE = "pause"                      # 暂停
    SKIP = "skip"                        # 跳过
    MODIFY_AND_CONTINUE = "modify"       # 修改参数后继续
```

## C.2 使用示例

```python
class SmartCSPlugin(PluginBase):
    """智能客服插件——自定义干预策略"""
    
    def __init__(self):
        super().__init__()
        self.hooks = self.CSHooks()
    
    class CSHooks(InterventionHooks):
        async def on_uncertain(self, context: dict) -> InterventionAction:
            # 涉及退款的场景强制转人工
            if context.get('intent') == 'refund_request':
                return InterventionAction.REQUIRE_APPROVAL
            return InterventionAction.ESCALATE_TO_HUMAN
        
        async def on_before_tool_call(self, tool_name: str, params: dict) -> InterventionAction:
            # 退款金额 > 500 元需要审批
            if tool_name == 'process_refund' and params.get('amount', 0) > 500:
                return InterventionAction.REQUIRE_APPROVAL
            return InterventionAction.ALLOW
        
        async def on_user_feedback(self, feedback: UserFeedback) -> None:
            # 所有差评自动创建 Jira ticket
            if feedback.rating <= 2:
                await create_jira_ticket(feedback)
```

---

## D：部署与依赖关系

```
部署顺序（Phase 2 完成后）：
1. SDK-1 (intervention_hooks)    ← 基础设施，最先完成
2. SDK-2 (execution_trace)       ← 基础设施
3. ddw-adapter-registry          ← 基础设施，不依赖 SDK 改动
4. ddw-sop-engine                ← 依赖 SDK-1
5. ddw-knowledge-hierarchy       ← 独立，不依赖其他
6. ddw-trace-panel               ← 依赖 SDK-2
7. ddw-persona-engine            ← 依赖 adapter-registry + sop-engine
8. ddw-feedback-loop             ← 依赖 trace-panel + persona-engine
```

---



## X. 插件入口（DDW 规范要求）

> 本 PRD 覆盖 3 个独立插件。每个插件需单独的 manifest.yaml 和 __init__.py。

### ddw-persona-engine

```python
# __init__.py
PLUGIN_NAME = "ddw-persona-engine"
PLUGIN_VERSION = "1.0.0"

def register(app, config=None):
    from .router import router
    app.include_router(router, prefix=f"/api/v1/plugins/{PLUGIN_NAME}", tags=[PLUGIN_NAME])
```

```yaml
# manifest.yaml
name: ddw-persona-engine
version: 1.0.0
description: "数字员工角色系统"
author: DDW Team
license: Apache-2.0
engine: ">=2.0.0"
isolation: inline
permissions:
  - "database:ddw_persona_engine"
dependencies:
  plugins:
    ddw-adapter-registry: ">=1.0.0"
    ddw-sop-engine: ">=1.0.0"
  python: [fastapi>=0.110, sqlalchemy>=2.0, pydantic>=2.0]
events:
  produces: ["persona.role.deployed", "persona.role.switched"]
  consumes: ["user.message.received"]
config:
  optional:
    default_role_ttl_minutes: 30
ecosystem:
  category: "core-engine"
  tags: ["persona", "role", "deployment"]
```

### ddw-feedback-loop

```python
# __init__.py
PLUGIN_NAME = "ddw-feedback-loop"
PLUGIN_VERSION = "1.0.0"

def register(app, config=None):
    from .router import router
    app.include_router(router, prefix=f"/api/v1/plugins/{PLUGIN_NAME}", tags=[PLUGIN_NAME])
```

```yaml
# manifest.yaml
name: ddw-feedback-loop
version: 1.0.0
description: "反馈收集与持续改进闭环"
author: DDW Team
license: Apache-2.0
engine: ">=2.0.0"
isolation: inline
permissions:
  - "database:ddw_feedback_loop"
  - "api:ddw-llm-gateway:read"
dependencies:
  plugins:
    ddw-trace-panel: ">=1.0.0"
    ddw-persona-engine: ">=1.0.0"
  python: [fastapi>=0.110, sqlalchemy>=2.0, pydantic>=2.0]
events:
  produces: ["feedback.analyzed", "feedback.fix_applied"]
  consumes: ["trace.span.completed"]
config:
  optional:
    batch_analysis_threshold: 10
    auto_fix_enabled: false
ecosystem:
  category: "quality"
  tags: ["feedback", "improvement", "pdca"]
```

### SDK 增强（PluginBase v2）— 不独立打包

SDK-1 (intervention_hooks) 和 SDK-2 (execution_trace) 直接修改 `sdk/plugin_base.py`，不创建独立插件。

```python
# sdk/plugin_base.py 增量修改
# 新增 InterventionHooks 类（见 Part C）
# 新增 ExecutionTrace 上下文管理器（见 PRD_ddw-trace-panel §二）
```

## E：灵感溯源

- **灵感来源**：StaffDeck 的"数字员工角色/工号/能力档案"概念 + "人工接管"机制 + "用户反馈闭环"
- **DDW 实现**：全新 Apache 2.0。Persona 系统参考了 Kubernetes Helm Chart 的"一键部署依赖"设计模式。Feedback Loop 参考了经典的 Plan-Do-Check-Act (PDCA) 质量管理循环。Intervention Hooks 参考了 Git Hooks 的拦截模式

---

*代码实现由 MiMo Code CLI 执行，DeepSeek V4 Flash 代码审查。此 PRD 覆盖 3 个组件，可并行开发。*
