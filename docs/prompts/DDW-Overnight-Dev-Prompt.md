# DDW AI Hub — 通宵开发全量提示词
# 时间窗口：今晚 → 明天 09:00（约 8 小时）
# 设备：Mac mini M4 16G
# 工具：MiniMax Code
# 目标：明早 9 点前产出完整可演示的 SaaS 界面 + 核心后端 + 培训插件

---

## 你是一个企业级 Python 全栈开发者

今晚你要为 DDW AI Hub（渡笃微AI底座平台）完成多个模块的开发。每个模块完成后必须自检，只有全部 PASS 才能进入下一个模块。代码保存到指定路径，32G 设备会直接读取。

## 第零步：读取上下文（必做，30 分钟内完成）

读取以下文件，理解项目全貌后才能开始编码：

```
# 核心架构
/Users/chenye/workspace/ddw-ai-hub/PRD/DDW_AI_Hub_v5.4_MASTER.md
/Users/chenye/workspace/ddw-ai-hub/docs/DDW_Architecture_Decision_Records.md
/Users/chenye/workspace/ddw-ai-hub/docs/DDW_SaaS_LastMile_Plan.md

# 前端规范
/Users/chenye/workspace/ddw-ai-hub/docs/DDW_Frontend_Design_Standard.md
/Users/chenye/workspace/ddw-ai-hub/docs/DDW_Frontend_UI_Architecture_Plan.md

# 现有代码模式（必须理解后复用，不要重写）
/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/core/main.py
/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/core/middleware/tenant.py
/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/core/database/models.py
/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/core/auth/jwt.py
/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/core/config.py
/Users/chenye/workspace/ddw-ai-hub/plugins/ddw-token-manager/models.py
/Users/chenye/workspace/ddw-ai-hub/plugins/ddw-token-manager/router.py
/Users/chenye/workspace/ddw-ai-hub/plugins/ddw-llm-gateway/manifest.yaml
/Users/chenye/workspace/ddw-ai-hub/plugins/ddw-smart-cs/manifest.yaml

# 前端视觉参考
/Users/chenye/workspace/ddw-ai-hub/frontend/DDW_Platform_Demo_v5.html

# 插件开发规范
/Users/chenye/workspace/ddw-ai-hub/docs/DDW_Plugin_Development_Guide.md
```

**读完后用 3 句话总结你对以下的理解：**
1. DDW 的 7 层架构
2. 插件继承规范（PluginBase + PluginState + manifest.yaml）
3. 前端设计规范（Ant Design OA 风格）

---

## 技术栈（必须遵守，不得引入额外框架）

- Python >= 3.11, < 3.14
- FastAPI >= 0.110.0 + Uvicorn
- SQLAlchemy >= 2.0.30（Async）
- PyJWT >= 2.8.0（RSA256）
- pytest >= 8.0
- 前端：纯 HTML + CSS + JS（不引入 React/Vue/Angular/任何 npm 包）
- 禁止：LangChain / LlamaIndex / CrewAI

---

## 前端设计规范（所有 HTML 页面必须遵守）

```
锚点：Ant Design 企业 OA（泛微/蓝凌/帆软风格）
主色：#1890FF
深色导航：#001529
成功色：#52C41A
警告色：#FAAD14
错误色：#F5222D
文字色：#333333（正文）/ #666666（次要）/ #999999（辅助）
背景色：#F0F2F5
圆角：≤ 2px（不要大圆角卡片！）
字体：-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif
间距：8px 基准网格

严格禁止：
❌ linear-gradient（渐变背景）
❌ box-shadow（阴影）
❌ emoji 图标（用 SVG 线条图标代替）
❌ 大圆角（>2px）
❌ AI-slop 词汇：赋能/助力/打造/闭环/护航/全方位/一站式/深度赋能/核心竞争力/底层逻辑/未来可期/降本增效

布局：
- 左侧深色导航栏（固定宽度 200px）
- 顶部标题栏（白色，含面包屑）
- 主内容区（灰色背景 #F0F2F5）
- 移动端响应式（导航折叠为汉堡菜单）
- 所有页面必须支持微信内打开（移动端友好）
```

---

## 模块 A：自动 ORM 租户隔离层（0.5 小时）

### A1：SQLAlchemy ORM 自动租户过滤

创建：`/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/core/database/tenant_filter.py`

要求：
- 使用 `contextvars.ContextVar` 存储当前请求的 tenant_id
- `set_tenant_context(tenant_id)` / `get_tenant_context()` 上下文管理器
- 监听 SQLAlchemy `before_flush` 事件：自动为 TenantMixin 新对象注入 tenant_id
- 监听 `do_orm_execute` 事件：自动为 SELECT 注入 `WHERE tenant_id = ?`
- `bypass_tenant_filter()` 跳过机制（admin 全局操作用）
- 在 main.py 的 lifespan 中注册事件监听器

### A2：租户服务

创建：`/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/core/services/tenant_service.py`

方法：
- `create_tenant(name, plan='free')` → 创建租户 + 默认 TokenQuota
- `get_tenant_by_id(tenant_id)`
- `upgrade_plan(tenant_id, new_plan)`
- `get_tenant_usage(tenant_id)` → 用量统计

### A3：自检

```bash
cd /Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub
python -c "from core.database.tenant_filter import set_tenant_context; print('OK')"
python -c "from core.services.tenant_service import create_tenant; print('OK')"
```

---

## 模块 B：SaaS 注册 + 套餐 + 管理后台（2 小时）

### B1：注册 API

修改：`/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/core/api/auth.py`

新增：
```
POST /api/v1/auth/register     → 手机号+验证码+企业名 → 创建 Tenant+User+TokenQuota → 返回 JWT
POST /api/v1/auth/send-code    → 发送手机验证码
GET  /api/v1/auth/me           → 当前用户信息
```

### B2：注册页面

创建：`/Users/chenye/workspace/ddw-ai-hub/frontend/saas-register.html`

内容：
- DDW Logo + "注册 DDW AI Hub"
- 手机号输入 + 验证码输入 + 获取验证码按钮（60 秒倒计时）
- 企业名称（可选）
- "免费注册" 按钮
- 底部："已有账号？直接登录"
- 成功后自动跳转到 saas-pricing.html

### B3：套餐选择页面

创建：`/Users/chenye/workspace/ddw-ai-hub/frontend/saas-pricing.html`

三个套餐卡片：

| 套餐 | 价格 | 用户数 | 功能 | 按钮 |
|:---|:---|:---|:---|:---|
| 免费版 | ¥0 | 5 | 基础 LLM 对话、社区支持 | "当前套餐" |
| 标准版 | ¥4,999 | 50 | 全部插件、邮件支持 | "立即升级" |
| 企业版 | ¥19,999 | 200 | FDE 现场、7×12 工单 | "联系我们" |

### B4：管理后台（5 个子页面）

创建：`/Users/chenye/workspace/ddw-ai-hub/frontend/saas-admin.html`

子页面：
- `#/overview`：套餐信息 + Token 消耗趋势图（纯 CSS 柱状图）+ API 调用统计 + 活跃用户数 + 插件排行
- `#/users`：用户表格 + 邀请/移除 + 角色切换
- `#/apikeys`：Key 列表 + 创建/禁用/删除
- `#/billing`：当前套餐 + 升级入口 + 用量预警
- `#/settings`：企业名修改 + 通知 + 安全

### B5：管理后台 API

修改：`/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/core/api/admin.py`

```
GET    /api/v1/admin/overview       → 用量概览
GET    /api/v1/admin/users          → 用户列表
POST   /api/v1/admin/users/invite   → 邀请用户
DELETE /api/v1/admin/users/{id}     → 移除用户
GET    /api/v1/admin/apikeys        → Key 列表
POST   /api/v1/admin/apikeys        → 创建 Key
DELETE /api/v1/admin/apikeys/{id}   → 删除 Key
GET    /api/v1/admin/billing        → 套餐信息
```

### B6：自检

```bash
# 编译检查
python -c "
import py_compile, os
for root, dirs, files in os.walk('core'):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if f.endswith('.py'):
            py_compile.compile(os.path.join(root, f), doraise=True)
print('compile OK')
"

# HTML 去 AI 化检查
python3 -c "
import os
ai_words = ['赋能','助力','打造','闭环','护航','全方位','一站式','深度赋能','核心竞争力','底层逻辑','未来可期','降本增效']
fd = '/Users/chenye/workspace/ddw-ai-hub/frontend'
for f in os.listdir(fd):
    if f.startswith('saas-') and f.endswith('.html'):
        c = open(os.path.join(fd,f)).read()
        found = [w for w in ai_words if w in c]
        bad = 'linear-gradient' in c or 'box-shadow' in c
        assert not found and not bad, f'{f}: AI-slop={found}, style-bad={bad}'
        assert len(c) > 2000, f'{f} too small'
        print(f'✅ {f}: {len(c)}B')
"
```

---

## 模块 C：HRIS 适配器（1.5 小时）

### C1：适配器基类 + 4 个实现

创建以下文件（所有路径相对于 `/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/`）：

```
core/hris_adapters/__init__.py
core/hris_adapters/base.py          ← BaseHRISAdapter 抽象基类
core/hris_adapters/kingdee.py       ← 金蝶适配器
core/hris_adapters/wecom.py         ← 企微通讯录适配器
core/hris_adapters/beisen.py        ← 北森适配器
core/hris_adapters/feishu.py        ← 飞书通讯录适配器
core/hris_adapters/dingtalk.py      ← 钉钉通讯录适配器
core/hris_adapters/manager.py       ← 适配器注册/管理
```

**BaseHRISAdapter 接口：**
```python
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

class BaseHRISAdapter(ABC):
    """HRIS 适配器基类 — 对接企业人事系统的标准接口"""
    
    @abstractmethod
    async def authenticate(self, config: dict) -> bool:
        """认证连接"""
        
    @abstractmethod
    async def sync_employees(self, since: Optional[str] = None) -> List[Dict]:
        """同步员工列表（增量）"""
        
    @abstractmethod
    async def get_employee(self, employee_id: str) -> Optional[Dict]:
        """查询单个员工"""
        
    @abstractmethod
    async def push_training_record(self, record: Dict) -> bool:
        """推送培训记录到人事系统"""
        # record = {user_id, course_id, duration, score, completed_at}
        
    @abstractmethod
    async def push_assessment_result(self, result: Dict) -> bool:
        """推送考核结果到人事系统"""
        # result = {user_id, assessment_id, score, grade, details}
```

**每个适配器的实现要求：**
- **金蝶**：REST API 调用，OAuth2 认证，员工/部门/培训记录 CRUD
- **企微**：通讯录 API（`/cgi-bin/user/list`），培训记录写入「汇报」或「日程」
- **北森**：开放平台 API，员工档案 + 培训模块对接
- **飞书**：通讯录 API + 多维表格（培训记录写入 Bitable）
- **钉钉**：通讯录 API + 智能人事（培训记录写入审批/日志）

每个适配器都必须：
1. 继承 BaseHRISAdapter
2. 实现全部 5 个抽象方法
3. 包含完整的错误处理和日志
4. 使用 httpx.AsyncClient 调用外部 API
5. 支持通过 DDW EventBus 订阅 `training.*` 事件自动推送记录

### C2：EventBus 集成

在 `core/hris_adapters/manager.py` 中实现：
- 监听 `training.session.completed` 事件 → 自动推送到 HRIS
- 监听 `training.assessment.completed` 事件 → 自动推送考核结果
- 支持配置哪些 HRIS 接收哪些事件

### C3：自检

```bash
python -c "
from core.hris_adapters.base import BaseHRISAdapter
from core.hris_adapters.kingdee import KingdeeAdapter
from core.hris_adapters.wecom import WeComAdapter
from core.hris_adapters.beisen import BeisenAdapter
from core.hris_adapters.feishu import FeishuAdapter
from core.hris_adapters.dingtalk import DingTalkAdapter
from core.hris_adapters.manager import HRISManager
print('All HRIS adapters import OK')
"
```

---

## 模块 D：MCP 协议适配层（1.5 小时）

### D1：MCP Server 实现

创建以下文件（所有路径相对于 `/Users/chenye/workspace/ddw-ai-hub/cloud-llm/ddw-ai-hub/`）：

```
core/mcp/__init__.py
core/mcp/server.py              ← MCP Server 核心（JSON-RPC 2.0 over stdio/SSE）
core/mcp/tools.py               ← DDW 工具注册表（暴露插件能力为 MCP tools）
core/mcp/resources.py           ← MCP Resources（暴露知识库/文档为 MCP resources）
core/mcp/protocol.py            ← MCP 协议消息定义
core/mcp/transport.py           ← 传输层（stdio + SSE + HTTP）
```

**MCP Server 核心功能：**

```python
class DDWMCPServer:
    """DDW AI Hub 的 MCP Server — 让外部 Agent 调用 DDW 能力"""
    
    # 暴露的 MCP Tools（从插件自动注册）
    # - ddw.llm.chat → LLM 对话
    # - ddw.kb.search → 知识库搜索
    # - ddw.training.start_session → 启动培训会话
    # - ddw.training.get_progress → 查询学习进度
    # - ddw.smart_cs.handle_message → 智能客服
    # - ddw.email.send → 邮件发送
    # - ddw.hris.sync_employees → 同步员工
    
    # 暴露的 MCP Resources
    # - ddw://knowledge-bases → 知识库列表
    # - ddw://plugins → 插件列表
    # - ddw://training/courses → 课程列表
    
    async def handle_request(self, request: dict) -> dict:
        """处理 MCP JSON-RPC 请求"""
        
    async def list_tools(self) -> list:
        """返回所有可用工具"""
        
    async def call_tool(self, name: str, arguments: dict) -> dict:
        """调用指定工具"""
        
    async def list_resources(self) -> list:
        """返回所有可用资源"""
        
    async def read_resource(self, uri: str) -> dict:
        """读取指定资源"""
```

**MCP 协议要求：**
- 遵循 MCP 2024-11-05 规范
- 支持 JSON-RPC 2.0 消息格式
- 支持三种传输：stdio（本地 CLI）、SSE（远程）、HTTP（RESTful）
- 工具描述自动生成（从插件 manifest.yaml 读取）
- 支持 `initialize` / `tools/list` / `tools/call` / `resources/list` / `resources/read`

### D2：MCP 配置端点

在 API 中新增：
```
GET  /api/v1/mcp/info         → MCP Server 信息（名称/版本/能力）
GET  /api/v1/mcp/sse          → SSE 传输端点
POST /api/v1/mcp/jsonrpc      → HTTP 传输端点
```

### D3：自检

```bash
python -c "
from core.mcp.server import DDWMCPServer
from core.mcp.tools import ToolRegistry
from core.mcp.resources import ResourceRegistry
print('MCP import OK')
"
```

---

## 模块 E：DDW 培训插件群（2 小时）

### E1：ddw-training 核心插件

创建插件目录：`/Users/chenye/workspace/ddw-ai-hub/plugins/ddw-training/`

```
plugins/ddw-training/
├── manifest.yaml               ← 插件清单
├── __init__.py
├── plugin.py                   ← PluginBase 继承
├── services/
│   ├── __init__.py
│   ├── socratic_engine.py      ← 苏格拉底对话引擎
│   ├── assessment_engine.py    ← AI 出题 + 自动评分
│   ├── progress_tracker.py     ← 学习进度追踪
│   └── courseware_manager.py   ← 课件管理（YAML 配置驱动）
├── config/
│   ├── subjects/
│   │   ├── physics.yaml        ← 初三物理配置
│   │   └── chemistry.yaml      ← 初三化学配置
│   └── pedagogy/
│       ├── socratic_lens.yaml  ← 4 维度教学审计
│       ├── six_moves.yaml      ← 6 思维动作
│       └── twelve_vignettes.yaml ← 12 图景
├── router.py                   ← API 路由
└── tests/
    └── test_training.py
```

**manifest.yaml：**
```yaml
name: ddw-training
version: 0.1.0
display_name: DDW 智能培训
description: 苏格拉底教学法 + 多媒体课件 + 自动评估
engine: plugin_base
isolation: inline
dependencies:
  plugins:
    ddw-llm-gateway: ">=1.0.0"
permissions:
  - llm.chat
  - event_bus.publish
config_schema:
  type: object
  properties:
    default_subject:
      type: string
      default: physics
    socratic_depth:
      type: integer
      default: 3
```

**Socratopia 教学法 YAML 配置（直接写入 config/pedagogy/）：**

`socratic_lens.yaml`：
```yaml
name: socratic-lens
dimensions:
  - id: conceptual_clarity
    name: 概念清晰度
    weight: 0.30
    desc: 学生是否真正理解核心概念
  - id: reasoning_depth
    name: 推理深度
    weight: 0.30
    desc: 思维是否从记忆上升到分析/评价/创造
  - id: engagement_quality
    name: 参与质量
    weight: 0.20
    desc: 学生是主动参与还是被动回答
  - id: pedagogical_alignment
    name: 教学法对齐度
    weight: 0.20
    desc: 是否遵循 6 思维动作 + 12 图景结构化路径
```

`six_moves.yaml`：
```yaml
name: six-thinking-moves
moves:
  - {id: 1, name: observe,     display: 观察, prompt: "请仔细观察这个现象/图表，你注意到了什么？", level: remember}
  - {id: 2, name: question,    display: 提问, prompt: "关于你观察到的，你有什么疑问？", level: understand}
  - {id: 3, name: hypothesize, display: 假设, prompt: "根据已有知识，你认为可能的解释是什么？", level: apply}
  - {id: 4, name: investigate, display: 探究, prompt: "我们来设计一个实验/推理来验证你的假设", level: analyze}
  - {id: 5, name: evaluate,    display: 评价, prompt: "你的假设被验证了吗？证据支持还是反驳了你的想法？", level: evaluate}
  - {id: 6, name: synthesize,  display: 综合, prompt: "总结我们今天学到了什么，和之前的知识有什么联系？", level: create}
```

`twelve_vignettes.yaml`：
```yaml
name: twelve-vignettes
vignettes:
  - {id: 1,  name: concrete_example,    display: 具体实例,   best_for: 概念引入}
  - {id: 2,  name: analogy,             display: 类比,       best_for: 难点突破}
  - {id: 3,  name: visual_diagram,      display: 可视化图解, best_for: 因果关系}
  - {id: 4,  name: interactive_sim,     display: 交互仿真,   best_for: 物理/化学实验}
  - {id: 5,  name: counter_example,     display: 反例,       best_for: 澄清误解}
  - {id: 6,  name: historical_context,  display: 历史脉络,   best_for: 科学史}
  - {id: 7,  name: problem_solving,     display: 解题演练,   best_for: 考试准备}
  - {id: 8,  name: debate,              display: 辩论,       best_for: 批判性思维}
  - {id: 9,  name: experiment_design,   display: 实验设计,   best_for: 科学方法}
  - {id: 10, name: concept_map,         display: 概念地图,   best_for: 知识整合}
  - {id: 11, name: game_challenge,      display: 游戏挑战,   best_for: 巩固练习}
  - {id: 12, name: real_world_app,      display: 现实应用,   best_for: 学习动机}
```

### E2：ddw-training 管理页面

创建：`/Users/chenye/workspace/ddw-ai-hub/frontend/ddw-training.html`

这是一个完整的培训管理界面，包含：

**子页面 1：课程列表 `#/courses`**
- 卡片网格展示已有课程
- 每个卡片：学科名称/年级/课时数/学生数
- "创建新课程" 按钮

**子页面 2：学习界面 `#/learn/{course_id}`**
- 三段式布局（和 Demo v5 的 AI 助手页面风格一致）
- 左侧：课程大纲树状图
- 中间：对话区（苏格拉底对话 + 多媒体课件展示区）
- 右侧：学习进度 + 评估结果

**子页面 3：评估报告 `#/assessment`**
- 学生列表 + 每个学生的 4 维度评分雷达图（纯 CSS 实现，不用 Chart.js）
- 学时统计
- 知识点掌握度热力图

**子页面 4：课件管理 `#/courseware`**
- 上传 PDF/教材 → AI 自动生成课件
- 课件类型：幻灯片/交互仿真/测验/PBL/白板
- 课件预览（iframe 嵌入）

### E3：自检

```bash
python -c "
from importlib.util import spec_from_file_location, module_from_spec
import os
plugin_dir = '/Users/chenye/workspace/ddw-ai-hub/plugins/ddw-training'
for f in ['manifest.yaml', 'plugin.py', 'services/socratic_engine.py', 
          'services/assessment_engine.py', 'services/progress_tracker.py',
          'config/pedagogy/socratic_lens.yaml', 'config/pedagogy/six_moves.yaml',
          'config/pedagogy/twelve_vignettes.yaml']:
    path = os.path.join(plugin_dir, f)
    assert os.path.exists(path), f'MISSING: {f}'
    print(f'✅ {f}')
print('ddw-training plugin structure OK')
"
```

---

## 模块 F：技能管理 + 数字员工（1 小时）

### F1：技能管理页面

创建：`/Users/chenye/workspace/ddw-ai-hub/frontend/ddw-skills.html`

内容：
- 技能列表表格（名称/类型/调用次数/状态/最后更新）
- 技能分类筛选（全部/对话/工具/数据/集成）
- 创建新技能按钮（打开表单：名称/描述/触发词/配置 YAML 编辑器）
- 技能详情弹窗（含调用日志、配置编辑、启用/禁用）

### F2：数字员工管理页面

创建：`/Users/chenye/workspace/ddw-ai-hub/frontend/ddw-agents.html`

内容：
- 6 个数字员工卡片（和 Demo v5 一致）：
  - 小智（AI 助手）— 全能型
  - 绿盾（合规审查员）— ESG/法规
  - 邮灵（邮件助理）— 收发/分类/回复
  - 数录（数据录入员）— OCR/表单
  - 审批通（流程审批）— 自动化审批
  - 知库（知识管理员）— 知识库维护
- 每个卡片：头像 SVG + 名称 + 岗位描述 + 状态（在线/离线/忙碌）
- 点击进入详情：技能配置 + 工作日志 + 对话历史 + 性能指标

### F3：自检

```bash
python3 -c "
import os
fd = '/Users/chenye/workspace/ddw-ai-hub/frontend'
for f in ['ddw-skills.html', 'ddw-agents.html', 'ddw-training.html']:
    path = os.path.join(fd, f)
    assert os.path.exists(path), f'{f} missing'
    c = open(path).read()
    ai_words = ['赋能','助力','打造','闭环','护航','全方位','一站式','深度赋能']
    found = [w for w in ai_words if w in c]
    assert not found, f'{f} AI-slop: {found}'
    assert len(c) > 3000, f'{f} too small'
    print(f'✅ {f}: {len(c)}B, no AI-slop')
"
```

---

## 模块 G：HRIS 管理页面（0.5 小时）

### G1：HRIS 集成管理页面

创建：`/Users/chenye/workspace/ddw-ai-hub/frontend/ddw-hris.html`

内容：
- 5 个 HRIS 适配器卡片（金蝶/企微/北森/飞书/钉钉）
- 每个卡片：名称 + 状态（已连接/未连接）+ 连接配置表单
- 连接配置表单（每个适配器不同）：
  - 金蝶：App Key + App Secret + 服务器地址
  - 企微：CorpID + AgentID + Secret
  - 北森：Client ID + Client Secret + 环境
  - 飞书：App ID + App Secret
  - 钉钉：App Key + App Secret
- 同步日志表格（时间/操作/状态/同步数量）
- 手动同步按钮

---

## 模块 H：最终集成 + 验收（0.5 小时）

### H1：全局自检

```bash
cd /Users/chenye/workspace/ddw-ai-hub

# 1. Python 编译检查
python -c "
import py_compile, os
errors = 0
for root, dirs, files in os.walk('cloud-llm/ddw-ai-hub/core'):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if f.endswith('.py'):
            try:
                py_compile.compile(os.path.join(root, f), doraise=True)
            except py_compile.PyCompileError as e:
                print(f'ERROR: {e}')
                errors += 1
for root, dirs, files in os.walk('plugins'):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if f.endswith('.py'):
            try:
                py_compile.compile(os.path.join(root, f), doraise=True)
            except py_compile.PyCompileError as e:
                print(f'ERROR: {e}')
                errors += 1
assert errors == 0, f'{errors} compile errors'
print(f'✅ All .py files compile OK')
"

# 2. HTML 去 AI 化全量检查
python3 -c "
import os
ai_words = ['赋能','助力','打造','闭环','护航','全方位','一站式','深度赋能','核心竞争力','底层逻辑','未来可期','降本增效']
fd = '/Users/chenye/workspace/ddw-ai-hub/frontend'
count = 0
for f in sorted(os.listdir(fd)):
    if f.endswith('.html'):
        c = open(os.path.join(fd,f)).read()
        found = [w for w in ai_words if w in c]
        has_gradient = 'linear-gradient' in c
        has_shadow = 'box-shadow' in c
        ok = not found and not has_gradient and not has_shadow
        status = '✅' if ok else '❌'
        print(f'{status} {f}: {len(c)}B')
        if not ok:
            print(f'   AI-slop={found} gradient={has_gradient} shadow={has_shadow}')
        count += 1
print(f'\nTotal: {count} HTML files checked')
"

# 3. 文件清单验证
echo '=== 新建文件清单 ==='
ls -la cloud-llm/ddw-ai-hub/core/database/tenant_filter.py
ls -la cloud-llm/ddw-ai-hub/core/services/tenant_service.py
ls -la cloud-llm/ddw-ai-hub/core/hris_adapters/*.py
ls -la cloud-llm/ddw-ai-hub/core/mcp/*.py
ls -la plugins/ddw-training/manifest.yaml
ls -la plugins/ddw-training/plugin.py
ls -la plugins/ddw-training/services/*.py
ls -la plugins/ddw-training/config/pedagogy/*.yaml
ls -la frontend/saas-register.html
ls -la frontend/saas-pricing.html
ls -la frontend/saas-admin.html
ls -la frontend/ddw-training.html
ls -la frontend/ddw-skills.html
ls -la frontend/ddw-agents.html
ls -la frontend/ddw-hris.html
```

### H2：Git 提交

```bash
cd /Users/chenye/workspace/ddw-ai-hub

git add -A
git commit -m "feat: overnight sprint — SaaS last-mile + HRIS + MCP + training plugin

Module A: ORM tenant isolation (SQLAlchemy events + contextvars)
Module B: SaaS registration + pricing + admin dashboard
Module C: HRIS adapters (Kingdee/WeCom/Beisen/Feishu/DingTalk)
Module D: MCP protocol support (JSON-RPC 2.0 + stdio/SSE/HTTP)
Module E: ddw-training plugin (Socratopia pedagogy + assessment)
Module F: Skills + digital employee management pages
Module G: HRIS integration management page

Design: Ant Design enterprise OA (#1890FF, ≤2px radius)
All HTML: zero AI-slop, zero gradients, zero shadows
[LLM: minimax-code]"

git log --oneline -5
```

---

## 产出文件完整清单

```
# ===== 模块 A：租户隔离 =====
cloud-llm/ddw-ai-hub/core/database/tenant_filter.py
cloud-llm/ddw-ai-hub/core/services/tenant_service.py
cloud-llm/ddw-ai-hub/core/services/__init__.py

# ===== 模块 B：SaaS 页面 =====
cloud-llm/ddw-ai-hub/core/api/auth.py              （修改，新增注册端点）
cloud-llm/ddw-ai-hub/core/api/admin.py              （修改，新增管理端点）
frontend/saas-register.html
frontend/saas-pricing.html
frontend/saas-admin.html

# ===== 模块 C：HRIS 适配器 =====
cloud-llm/ddw-ai-hub/core/hris_adapters/__init__.py
cloud-llm/ddw-ai-hub/core/hris_adapters/base.py
cloud-llm/ddw-ai-hub/core/hris_adapters/kingdee.py
cloud-llm/ddw-ai-hub/core/hris_adapters/wecom.py
cloud-llm/ddw-ai-hub/core/hris_adapters/beisen.py
cloud-llm/ddw-ai-hub/core/hris_adapters/feishu.py
cloud-llm/ddw-ai-hub/core/hris_adapters/dingtalk.py
cloud-llm/ddw-ai-hub/core/hris_adapters/manager.py

# ===== 模块 D：MCP 协议 =====
cloud-llm/ddw-ai-hub/core/mcp/__init__.py
cloud-llm/ddw-ai-hub/core/mcp/server.py
cloud-llm/ddw-ai-hub/core/mcp/tools.py
cloud-llm/ddw-ai-hub/core/mcp/resources.py
cloud-llm/ddw-ai-hub/core/mcp/protocol.py
cloud-llm/ddw-ai-hub/core/mcp/transport.py

# ===== 模块 E：培训插件 =====
plugins/ddw-training/manifest.yaml
plugins/ddw-training/__init__.py
plugins/ddw-training/plugin.py
plugins/ddw-training/services/__init__.py
plugins/ddw-training/services/socratic_engine.py
plugins/ddw-training/services/assessment_engine.py
plugins/ddw-training/services/progress_tracker.py
plugins/ddw-training/services/courseware_manager.py
plugins/ddw-training/config/subjects/physics.yaml
plugins/ddw-training/config/subjects/chemistry.yaml
plugins/ddw-training/config/pedagogy/socratic_lens.yaml
plugins/ddw-training/config/pedagogy/six_moves.yaml
plugins/ddw-training/config/pedagogy/twelve_vignettes.yaml
plugins/ddw-training/router.py
plugins/ddw-training/tests/test_training.py

# ===== 模块 F：技能+数字员工 =====
frontend/ddw-skills.html
frontend/ddw-agents.html

# ===== 模块 G：HRIS 管理 =====
frontend/ddw-training.html
frontend/ddw-hris.html

# 总计：约 35 个文件
```

---

## 执行规则

1. **严格按模块顺序执行**：A → B → C → D → E → F → G → H，不要跳过
2. **每个模块完成后必须自检**：运行该模块的自检命令，只有全部 PASS 才进入下一个
3. **如果有 FAIL**：修复后重新运行自检，不要跳过
4. **Git 提交**：模块 A+B 完成后提交一次，C+D 完成后提交一次，E+F+G 完成后提交一次，H 最终提交
5. **代码完整性**：每个 .py 文件必须是完整可运行的，不要 stub 或 TODO
6. **前端去 AI 化**：每个 HTML 文件生成后立即运行去 AI 化检查
7. **保存路径**：所有文件保存到 `/Users/chenye/workspace/ddw-ai-hub/` 下

## 开始执行

读完所有上下文文件后，用 3 句话总结你的理解，然后从模块 A 开始。
