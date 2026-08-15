# DDW AI Hub SaaS 产品需求文档（PRD）

> 版本：v1.0 | 日期：2026-08-10 | 作者：Hermes Agent + 用户  
> 状态：待用户确认后开发

---

## 一、产品定位

DDW AI Hub 是面向企业的 AI 智能应用平台，提供 SaaS 多租户版和独立部署版。  
核心价值：让企业零门槛接入 AI 能力——数字员工、知识库、零代码流程、LLM 网关一站式解决。

## 二、目标用户

| 角色 | 说明 |
|------|------|
| superadmin | 平台超级管理员（锐果团队） |
| owner | 租户公司级管理员（如嘉必优 CIO 万永刚） |
| admin | 部门级管理员（由 owner 指定） |
| chairman | 董事长角色（由 owner 指定，默认可见全部报表） |
| finance | 财务员工（由 owner 指定的 1-3 人，可见财务模块） |
| member | 普通员工 |

## 三、产品频道总图（v3）

```
saas-admin.html 侧栏
│
├─ 🤖 DDW Pal（默认首登界面）
│   ├─ 用户自建 skill（YAML 编辑器）
│   ├─ 日常 AI 对话分析窗口
│   └─ 可嵌入泛微 OA
│
├─ 🏢 AI 组织
│   ├─ 部门（11 个预设，公司级可改名称/介绍）
│   ├─ 数字员工（部门级可配名称/技能）
│   └─ 员工（可导入，可同步泛微组织架构）
│
├─ 📚 知识库（公司/部门/员工 三层权限）
│
├─ 🪙 Token 广场（原 LLM 网关）
│   ├─ LLM 配置（10 类能力 × N 个 provider）
│   ├─ 消耗统计（员工/部门/公司/董事长 四级 ACL）
│   └─ API Key 管理（仅公司级）
│
├─ 🔌 插件市场
│   ├─ 全员可见，可试用（15 天）
│   ├─ 上传自制插件（15% 平台费率 + 合规提示）
│   └─ 公司/部门管理员可管理
│
├─ 💬 插件论坛（企业内部 GitHub）
│   ├─ 发布/点赞/评论/讨论
│   ├─ 提需求/需求闭环
│   └─ 加贡献者
│
├─ 🌊 碳硅协作空间（零代码 DAG 流程设计器）
│   ├─ 拖拽式流程编辑（ReactFlow）
│   ├─ 员工级/跨部门审核流
│   └─ 版本控制 + 公司级统计看板
│
├─ 👥 成员管理
│
├─ 💰 财务（仅 owner + 指定财务员工）
│   ├─ 套餐与账单
│   └─ 发票管理
│
└─ ⚙️ 设置（偏好设置）
```

## 四、关键业务规则

| # | 规则 | 说明 |
|---|------|------|
| R1 | 平台默认 LLM 隐藏 | SaaS 默认提供 MiniMax M3 云端 LLM，**对所有用户不可见**，用量显示"平台公用 LLM" |
| R2 | LLM 三级自选 | 公司级管理员可开启"员工自选 LLM"开关；开启后员工可从公司已配置的 ≥2 个 LLM 中选择 |
| R3 | Skill 不可删除 | Skill 只允许 enabled/disabled 状态切换，任何层级都不能删除（员工停用≠删除） |
| R4 | 流程审核 | 员工级流程立即可用；跨部门流程需相关部门管理员审核后才能启用 |
| R5 | 财务隔离 | 套餐/账单/发票仅 owner + 指定的 1-3 个 finance 角色员工可见 |
| R6 | 董事长看板 | owner 可设置"chairman"角色，该角色默认可见全部报表和所有部门 token 消耗 |
| R7 | 插件试用 15 天 | 员工试用插件默认 15 天；到期弹窗提示联系管理员；管理员可见试用账号/频率/token |
| R8 | 插件市场费率 | 上传自制插件页面明确标注：平台收取 15% 服务器资源费 + 开票税点 + 个税代扣法律提示 |
| R9 | DDW Pal 默认首登 | 用户登录后默认进入 DDW Pal 界面（非 saas-admin 仪表盘） |
| R10 | 泛微 OA 同步 | 支持从泛微 E9 同步组织架构/人员/权限信息 |

## 五、技术栈

| 层 | 技术 |
|----|------|
| 前端 | 原生 HTML + CSS（DDW 主题变量）+ ReactFlow（碳硅协作空间） |
| 后端 | FastAPI + SQLAlchemy（async）+ SQLite |
| LLM 网关 | 自研 `core/llm_gateway/`（多 provider 路由） |
| 插件体系 | `load_plugins()` 动态加载，Plugin.__init__(app, config, manifest) |
| 部署 | ECS (Caddy) + 32G Mac mini + 16G Mac mini |

## 六、关联文档索引

| 文档 | 路径 |
|------|------|
| AI 组织（11 部门） | `TASK_SPEC_AI_ORG.md` |
| Skill 池 | `TASK_SPEC_SKILL_POOL.md` |
| Token 广场 | `TASK_SPEC_TOKEN_PLAZA.md` |
| 插件市场 | `TASK_SPEC_PLUGIN_MARKETPLACE.md` |
| 插件论坛 | `TASK_SPEC_PLUGIN_FORUM.md` |
| 碳硅协作空间 | `TASK_SPEC_CARBON_SILICON.md` |
| DDW Pal | `TASK_SPEC_DDW_PAL.md` |
| 知识库 | `TASK_SPEC_KNOWLEDGE_BASE.md` |
| 泛微同步 | `TASK_SPEC_WECOM_SYNC.md` |
| 财务 ACL | `TASK_SPEC_FINANCE_ACL.md` |
| 登录+侧栏 | `TASK_SPEC_LOGIN_SIDEBAR.md` |
