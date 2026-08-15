# DDW AI Hub — 架构决策记录（ADR）
> 日期：2026-08-02
> 状态：已确认（用户拍板）

---

## ADR-001: 前端架构 = Web App + IM Skill 双轨

**决策**：DDW 的客户触达采用双轨路线，不建独立桌面客户端。

| 路径 | 触达方式 | 用途 |
|:---|:---|:---|
| 路径 1（已有） | 钉钉/飞书/企微 IM 机器人 | 日常查询/审批/问答 |
| 路径 2（新建） | 浏览器 Web App | 多媒体课件/交互仿真/白板/3D/培训 |

**理由**：
1. IM 消息格式无法渲染 iframe/Canvas/WebGL 内容
2. Web App 可完整承载 OpenMAIC 级别的多媒体课件
3. 独立客户端（Electron/Tauri）维护成本过高，不适合小团队
4. SaaS 模式（浏览器访问）才是真正的"零部署"

**参考**：Dify/FastGPT/Coze 都是 Web App 模式

---

## ADR-002: 多媒体课件播放器 = 参考 OpenMAIC，不重复造轮子

**决策**：ddw-training 的多媒体课件播放器参考 OpenMAIC 项目实现。

### OpenMAIC 渲染架构（已源码验证）

| 媒体类型 | 渲染技术 | OpenMAIC 源码位置 |
|:---|:---|:---|
| **交互仿真** | AI 生成自包含 HTML → `<iframe srcdoc>` + 池化管理 | `components/scene-renderers/InteractiveIframeHost.tsx` |
| **幻灯片** | Canvas 编辑器 + ProseMirror 富文本 + SVG 元素 | `components/slide-renderer/Editor/Canvas/` |
| **白板** | Framer Motion 动画 + PPT 元素逐步揭示 | `components/whiteboard/whiteboard-canvas.tsx` |
| **测验** | React 组件（QuizRenderer + 评分引擎 + 持久化） | `components/scene-renderers/quiz-renderer.tsx` |
| **PBL** | 多 Agent 工作区（角色选择+聊天+议题板） | `components/scene-renderers/pbl-renderer.tsx` |
| **TTS** | API 生成音频 → HTML5 Audio 播放器 | `app/api/generate/tts/route.ts` |
| **3D/游戏** | `<iframe>` 内 WebGL/Canvas 游戏引擎 | 同 InteractiveIframeHost |

### 核心洞察：交互仿真 = iframe srcdoc 池化

```
AI 生成自包含 HTML（含 CSS + JS + Canvas/WebGL）
    ↓
patchHtmlForIframe() 安全修补（沙箱、样式隔离）
    ↓
<iframe srcdoc={patchedHtml}> 嵌入页面
    ↓
InteractiveIframeHost 管理 iframe 生命周期池
  - 跨场景切换保持存活（避免重载）
  - Portal 渲染到 document.body
  - position: fixed 定位覆盖在场景槽位上
```

### DDW 复用清单

| OpenMAIC 组件 | 复用方式 | 优先级 |
|:---|:---|:---|
| InteractiveIframeHost + iframe 池管理 | 直接移植到 DDW Web App | P0 |
| SlideRenderer（含 Canvas 编辑器） | 作为独立 npm 包引入 | P1 |
| QuizRenderer + 评分引擎 | 翻译为 Python 版（DDW 插件规范） | P1 |
| WhiteboardCanvas + 动画系统 | 移植到 DDW Web App | P1 |
| PBL 渲染器 + MCP Agent 协作 | 翻译为 DDW EventBus + Agent 插件 | P2 |
| patchHtmlForIframe() 安全修补函数 | 直接移植 | P0 |
| AI 生成 prompt 模板（47 个 .md 文件） | 翻译为 ddw-training 的 prompt 配置 | P1 |

---

## ADR-003: MCP 协议支持 = 2026 企业级标配

**决策**：MCP（Model Context Protocol）必须作为 DDW 平台的一等公民支持。

**理由**：
1. 阿里百炼已全面支持 MCP（2025-04，50+ MCP 服务）
2. 钉钉悟空用 Skills，WorkBuddy 用 MCP，飞书 aily 原生支持
3. 企业客户普遍要求内部工具能通过 MCP 接入 Agent
4. 不支持 MCP = 被主流生态排斥

**优先级**：P1（排在 SaaS 最后一公里之后）

**技术方案**：待调研（已加入知识库待办）

---

## ADR-004: SaaS 托管能力 = 底座已有 80%，补最后 20%

**决策**：DDW 底座已具备多租户+认证+额度管理+审计，补齐注册+支付+管理页面即可。

### 已有的 SaaS 能力（代码验证）

| 能力 | 状态 | 证据 |
|:---|:---|:---|
| 多租户隔离 | ✅ 完整 | `TenantMixin` 20+ 表继承，`core/middleware/tenant.py` |
| 租户管理 | ✅ 完整 | `Tenant` 独立模型，`core/database/models.py:77` |
| 用户系统 | ✅ 完整 | `User` 模型含角色/权限/租户绑定 |
| JWT 认证 | ✅ 完整 | RSA256 + PIN + SMS + 白名单 |
| Token 额度管理 | ✅ 完整 | `ddw-token-manager` 插件：TokenQuota + ConsumeLog + SubscriptionInfo |
| 审计日志 | ✅ 完整 | `AuditLog` 模型 + `TenantMixin` |
| 双模式部署 | ✅ 完整 | Standalone=SQLite / Cloud=PostgreSQL |
| ECS 生产环境 | ✅ 运行中 | `ddw.9cio.com`（Caddy + PostgreSQL + systemd） |
| SaaS→RaaS 转型规划 | ✅ 文档齐全 | 43KB 完整规划文档 |

### 缺失的"最后一公里"

| # | 任务 | 优先级 | 工作量 | 依赖 |
|:---|:---|:---|:---|:---|
| 1 | 用户自助注册页面（手机号+验证码） | P0 | 1 周 | 无 |
| 2 | 套餐选择页面（免费/标准/企业） | P0 | 3 天 | 无 |
| 3 | 微信支付集成 | P0 | 1 周 | 需微信商户号 |
| 4 | 租户自助管理后台 | P1 | 2 周 | 注册+支付完成 |
| 5 | SaaS 域名绑定 | P2 | 1 周 | 前 4 项完成 |

---

## ADR-005: ddw-training 插件 = 1 核心 + 4 配套（插件组合式架构）

**决策**：ddw-training 是唯一核心培训插件，配套插件通过 EventBus 解耦协作。

| 场景 | ddw-training | ddw-report | ddw-employee-roster | ddw-kpi | ddw-saas-billing |
|:---|:---:|:---:|:---:|:---:|:---:|
| A. 自家孩子（初三物理/化学） | ✅ | ✅ | — | — | — |
| B. 同学家长（C 端 SaaS） | ✅ | ✅ | — | — | ✅ |
| C. 企业（独立部署） | ✅ | ✅ | ✅ | ✅ | — |
| D. 企业（SaaS 订阅） | ✅ | ✅ | ✅ | ✅ | ✅ |

**Socratopia 教学法**：4 维度审计 + 6 思维动作 + 12 图景（YAML 配置驱动）

---

## 技术栈确认

| 层 | 技术 | 版本 |
|:---|:---|:---|
| 后端 | Python / FastAPI / SQLAlchemy | 3.11+ / 0.110+ / 2.0+ |
| 前端（Web App） | Next.js 或 Vue3（待确认） | — |
| 数据库（Cloud） | PostgreSQL | 15 |
| 数据库（Standalone） | SQLite | 3.40+ |
| LLM Gateway | MiniMax M3 → DeepSeek V4 Pro → Ollama 三级 | — |
| IM 适配器 | 钉钉(Stream)/飞书/企微/微信 | — |
| 禁用 | LangChain / LlamaIndex / CrewAI | — |
