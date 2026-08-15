# DDW AI Hub — StaffDeck 灵感迁移路线图 v1.0

> 创建日期：2026-07-31
> 来源：StaffDeck (OpenBMB, AGPL-3.0, github.com/OpenBMB/StaffDeck) 深度研究
> 策略：策略 B — 仅提取设计思路，DDW 全新 Apache 2.0 实现
> DDW 上 GitHub 日期：2026-07-13（早于 StaffDeck 的 2026-07-15，不存在抄袭）

---

## 一、DDW 当前插件版图（基线）

### 已有插件（4 个正式 + 3 个独立仓）

| 插件 | 文件数 | 状态 | 说明 |
|:-----|:------:|:----:|:-----|
| `ddw-llm-gateway` | 19 .py | ✅ 已发布 | LLM 统一网关，One API 架构参考 |
| `ddw-token-manager` | 10 .py | ✅ 已发布 | Token 配额管理与成本控制 |
| `ddw-smart-cs` | 12 .py | ✅ 已发布 | 智能客服核心，AdapterBase 接口 |
| `ddw-email-assistant` | 16 .py | ✅ 已发布 | 邮件 AI 助手，IMAP/SMTP |
| `ddw-iot-dc3-connector` | 39 files | ✅ 已发布 | IoT DC3 连接器（AGPL 合规） |
| `ddw-ai-hub-mimo` | 4531 files | 🟡 独立仓 | MiMo Code AI 编码助手集成 |
| `ddw-esg-*` (6 plugins) | — | 🟡 私有仓 | ESG 套件（Gitea only） |

### SDK 基础设施

| 模块 | 大小 | 说明 |
|:-----|:----:|:-----|
| `plugin_base.py` | 2,183 B | PluginBase ABC + 生命周期管理 |
| `plugin_state.py` | 2,132 B | 5 态状态机（unloaded→loaded→active→paused→error） |
| `tool_def.py` | 2,594 B | Tool 定义 + MCP readOnlyHint 支持 |
| `config_manager.py` | 1,143 B | 插件配置管理 |
| `config_hash.py` | 2,017 B | 配置哈希校验 |
| `i18n.py` | 2,057 B | 国际化框架 |
| `shutdown.py` | 1,814 B | 优雅关闭 |

### 现有 PRD 文档

| PRD | 状态 |
|:----|:----:|
| `PRD_ddw-email-assistant_v1.0.0.md` | ✅ |
| `PRD_smart-cs_v1.0.md` | ✅ |
| `PRD_v5.7_engineering_roadmap.md` | ✅ |
| `DDW_Plugin_Development_Guide.md` | ✅ |

---

## 二、StaffDeck → DDW 灵感迁移全景

```
StaffDeck 核心能力              DDW 对应的改进/新建
─────────────────────────────────────────────────
① 状态机 SOP 引擎        ──→  🆕 ddw-sop-engine（新建）
② 层级知识检索            ──→  🆕 ddw-knowledge-hierarchy（新建）
③ IM 适配器注册表         ──→  🔧 ddw-adapter-registry（升级已有 AdapterBase）
④ Agent 友好部署          ──→  🔧 README 增加一键部署 Prompt
⑤ 人工接管+反馈闭环      ──→  🔧 PluginBase 增强 + 🆕 ddw-feedback-loop
⑥ 技能市场 Fork          ──→  🔧 Plugin Marketplace 增强
⑦ 数字员工角色系统        ──→  🆕 ddw-persona-engine（新建）
⑧ 内置任务调度器          ──→  🆕 ddw-scheduler（新建）
⑨ 多员工协同+群聊        ──→  🔧 ddw-smart-cs 增强
⑩ 完整 Trace 面板         ──→  🆕 ddw-trace-panel（新建）
```

---

## 三、分阶段执行计划

### Phase 1：基础设施增强（Week 1-2，7 月 31 日起）

**目标**：补齐 DDW 底座缺失的核心引擎，不涉及前端改动。

| 优先级 | 编号 | 任务 | 类型 | 预估工期 | PRD 状态 |
|:------:|:----:|:-----|:----:|:--------:|:--------:|
| **P0** | SOP-1 | 🆕 `ddw-sop-engine` — 状态机 SOP 编排引擎 | 新建插件 | 5-7天 | ⏳ 本会话撰写 |
| **P0** | KNW-1 | 🆕 `ddw-knowledge-hierarchy` — 层级知识检索引擎 | 新建插件 | 5-7天 | ⏳ 本会话撰写 |
| **P0** | SDK-1 | 🔧 PluginBase 增加 `intervention_hooks`（接管钩子） | SDK 增强 | 1-2天 | 嵌入 SOP PRD |
| **P0** | SDK-2 | 🔧 PluginBase 增加 `execution_trace` 上下文管理器 | SDK 增强 | 1-2天 | 嵌入 Trace PRD |

**依赖关系**：
```
SDK-1 (intervention_hooks) ← SOP-1 依赖
SDK-2 (execution_trace)    ← TRC-1 依赖
SOP-1 和 KNW-1 可并行开发（无依赖）
```

---

### Phase 2：可观测性与渠道统一（Week 3-4）

| 优先级 | 编号 | 任务 | 类型 | 预估工期 | PRD 状态 |
|:------:|:----:|:-----|:----:|:--------:|:--------:|
| **P1** | TRC-1 | 🆕 `ddw-trace-panel` — 完整 Trace 可观测性 | 新建插件+前端 | 5-7天 | ⏳ 本会话撰写 |
| **P1** | ADT-1 | 🔧 `ddw-adapter-registry` — IM 适配器统一注册表 | 重构现有 | 3-5天 | ⏳ 本会话撰写 |
| **P1** | ADT-2 | 🔧 升级 `ddw-smart-cs` — 意图自动路由 + 群聊止血 | 增强现有 | 2-3天 | 嵌入 Adapter PRD |

---

### Phase 3：角色系统与反馈闭环（Week 5-6）

| 优先级 | 编号 | 任务 | 类型 | 预估工期 | PRD 状态 |
|:------:|:----:|:-----|:----:|:--------:|:--------:|
| **P2** | PRS-1 | 🆕 `ddw-persona-engine` — 数字员工角色系统 | 新建插件 | 3-5天 | 📋 待撰写 |
| **P2** | FBK-1 | 🆕 `ddw-feedback-loop` — 反馈收集与持续改进 | 新建插件 | 3-5天 | 📋 待撰写 |
| **P2** | FBK-2 | 🔧 升级 Plugin Marketplace — 技能 Fork + 版本管理 | 增强现有 | 2-3天 | 📋 待撰写 |

---

### Phase 4：调度器与一键部署（Week 7-8）

| 优先级 | 编号 | 任务 | 类型 | 预估工期 | PRD 状态 |
|:------:|:----:|:-----|:----:|:--------:|:--------:|
| **P3** | SCH-1 | 🆕 `ddw-scheduler` — 内置任务调度器 | 新建插件 | 2-3天 | 📋 待撰写 |
| **P3** | DOC-1 | 🔧 全部 README 增加 Agent-Friendly Deploy Prompt | 文档增强 | 1天 | 📋 待撰写 |
| **P3** | GRP-1 | 🔧 `ddw-smart-cs` 增加群聊多角色协作 | 增强现有 | 3-5天 | 嵌入 Persona PRD |

---

## 四、DDW 插件最终版图（Phase 4 完成后）

```
DDW AI Hub 插件生态
│
├── 🔌 核心引擎层（本路线图新建）
│   ├── ddw-sop-engine          ← 状态机 SOP 编排
│   ├── ddw-knowledge-hierarchy ← 层级知识检索
│   ├── ddw-persona-engine      ← 角色装配系统
│   ├── ddw-scheduler           ← 内置任务调度
│   ├── ddw-feedback-loop       ← 反馈闭环
│   └── ddw-trace-panel         ← 可观测性
│
├── 🔧 基础设施层（增强）
│   ├── ddw-adapter-registry    ← IM 适配器注册表（升级）
│   ├── PluginBase v2           ← 增强 intervention_hooks + execution_trace
│   └── Plugin Marketplace v2   ← 增加 Fork + 版本管理
│
├── 📦 业务插件层（已有）
│   ├── ddw-llm-gateway         ← LLM 统一网关
│   ├── ddw-token-manager       ← Token 配额管理
│   ├── ddw-smart-cs            ← 智能客服（增强版）
│   ├── ddw-email-assistant     ← 邮件助手
│   └── ddw-iot-dc3-connector   ← IoT 连接器
│
└── 🎯 角色模板层（Phase 3 实现）
    ├── 客服角色 = smart-cs + knowledge-hierarchy + adapter-wecom + feedback-loop
    ├── 数据分析师 = scheduler + llm-gateway + trace-panel
    └── ...（社区贡献）
```

---

## 五、法律合规声明

| 事项 | 措施 |
|:-----|:-----|
| StaffDeck 许可证 | AGPL-3.0（传染性 Copyleft） |
| DDW 许可证 | Apache 2.0 |
| 策略 | **策略 B**：仅提取设计思路 → Mermaid 流程图 → DDW 全新 Python 实现 |
| 代码隔离 | 所有新插件不包含、不引用、不翻译 StaffDeck 任何源码（含注释/变量名/函数签名） |
| 设计溯源 | 每个新插件的 PRD 中标注"灵感来源：StaffDeck 的 XXX 概念（AGPL-3.0），DDW 为全新 Apache 2.0 实现" |
| 推送验证 | Phase 9 脱敏审计增加检查项：`grep -rni "staffdeck\|staff_deck"` 返回 0 结果 |

---

## 六、开发工具链

按用户铁律（2026-07-14 拍板）：

| 环节 | 工具 | 执行位置 |
|:-----|:-----|:---------|
| **PRD 撰写** | Hermes Agent（DeepSeek V4 Pro） | 32G Mac mini |
| **架构决策** | Hermes Agent | 32G Mac mini |
| **编码实现** | MiMo Code CLI（`~/.mimocode/bin/mimo`） | 32G Mac mini（00:00-08:00 折扣窗口） |
| **代码审查** | DeepSeek V4 Flash（128G 本地，ds4-server） | 128G MBP |
| **测试验证** | MiMo Code CLI + pytest | 32G Mac mini |
| **Git 推送** | Hermes Agent（调度）→ Gitea（私有）/ GitHub（确认后） | 32G Mac mini |

---


> **合规检查通过（2026-08-01）**：所有 PRD 已按 DDW 插件开发规范 §4 (manifest) + §5 (ORM) + §6 (API prefix) 完成格式修正。
> 具体修正：API 前缀统一为 `/api/v1/plugins/{name}/`、manifest 采用 `config.optional` 格式、补充 `engine/isolation/permissions/events` 字段、添加 `register(app)` + `/health` 标准端点。

## 七、下一步行动

1. ✅ Master Roadmap 已完成（本文档）
2. ⏳ 撰写 PRD_ddw-sop-engine_v1.0.md
3. ⏳ 撰写 PRD_ddw-knowledge-hierarchy_v1.0.md
4. ⏳ 撰写 PRD_ddw-trace-panel_v1.0.md
5. ⏳ 撰写 PRD_ddw-adapter-registry_v1.0.md

---
*本路线图遵循 DDW 插件开发流程 Phase 1-4 规范，每个插件在编码前需完成门禁 ① 确认。*
