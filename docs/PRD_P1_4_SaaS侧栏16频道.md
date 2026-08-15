# PRD: SaaS 管理后台侧栏 11 频道补齐（P1-4）

> 编号：PRD-P1-4-SAASCHANNELS
> 版本：v1.0
> 日期：2026-08-11
> 优先级：P1（Demo 后重点，客户直接感知的频道化呈现）
> 关联铁律：铁律1（冒烟）、铁律2（API契约）、铁律4（边界——本期只做频道入口+占位数据，不做承诺外功能）
> 关联规范：DDW-代码命名规范与入库规范-20260811.md

---

## 1. 背景与目标

### 1.1 问题
saas-admin.html 侧栏仅 6 项（数据概览/成员管理/API Key/套餐与账单/发票管理/偏好设置），客户期望看到 11 个频道（LLM 配置/知识库/数字员工/Skill/碳硅广场/DDW Pal/插件管理/插件论坛/经销商/客户Demo账号/文档）。

### 1.2 目标（边界内）
本期只做**侧栏频道入口 + 频道页框架 + 已有后端数据的展示**：
- 已有后端 API 的频道 → 真实数据展示
- 尚无后端 API 的频道 → 频道页显示"规划中"状态页（灰显 + 说明文案，符合"列出全部+灰显未上线"原则）
- 不做：泛微同步/碳硅广场核心功能/DDW Pal 完整版（属 P2）

## 2. 侧栏频道清单（11+2）

| # | 频道 | 路由 | 数据源 | 本期状态 |
|---|------|------|--------|---------|
| 1 | 数据概览 | #/overview | /admin/overview + /admin/llm/usage | ✅ 已有 |
| 2 | 成员管理 | #/users | /users/ | ✅ 已有 |
| 3 | LLM 配置 | #/llm | /llm/providers + /llm/rules | 🟡 展示已有数据 |
| 4 | 知识库 | #/knowledge | /plugins/ddw-knowledge-*/ | 🟡 展示已有数据或空态 |
| 5 | 数字员工 | #/agents | /plugins/ddw-agents/ | 🟡 空态+规划中 |
| 6 | 技能 Skill | #/skills | /plugins/ddw-skills/ | 🟡 空态+规划中 |
| 7 | 碳硅广场 | #/carbon | 无 | ⚪ 规划中（v2.0） |
| 8 | DDW Pal | #/pal | 无 | ⚪ 规划中（v2.0） |
| 9 | 插件管理 | #/plugins | /admin/plugins | ✅ 已有（改显示已装/未装） |
| 10 | 插件论坛 | #/forum | /plugins/ddw-forum/ | 🟡 空态+规划中 |
| 11 | 经销商 | #/partners | /plugins/ddw-partner-directory/ | ✅ 已有 |
| 12 | 客户 Demo 账号 | #/demo-accounts | /plugins/ddw-partner-directory/demo-accounts | ✅ 已有 |
| 13 | API Key | #/apikey | 已有 | ✅ 已有 |
| 14 | 套餐与账单 | #/billing | 已有 | ✅ 已有 |
| 15 | 发票管理 | #/invoices | 已有 | ✅ 已有 |
| 16 | 偏好设置 | #/preferences | 已有 | ✅ 已有 |

## 3. 实现要点

### 3.1 侧栏结构（saas-admin.html）
```
- 分组标题：总览 / AI 能力 / 企业管理 / 平台
- 每项：图标 + 名称 + 状态标（(已上线)/(8/30)）
- 点击 → hash 路由切换内容区（不整页刷新）
```

### 3.2 频道页通用框架
```html
<div class="channel-page" id="page-llm">
  <div class="channel-header">
    <h2>LLM 配置</h2>
    <span class="badge badge-on">已上线</span>
  </div>
  <div class="channel-body"><!-- 内容或规划中占位 --></div>
</div>
```

### 3.3 规划中占位（灰显）
```html
<div class="empty-plan">
  <div class="icon">🚧</div>
  <h3>碳硅广场</h3>
  <p>该频道正在规划中，预计 8 月 30 日 v2.0 上线</p>
</div>
```

### 3.4 后端补充（如缺失）
```python
# 若有频道需要后端统计端点
GET /api/v1/admin/channels/status
→ {"items": [
    {"key":"llm","name":"LLM 配置","status":"live","url":"/llm/providers"},
    {"key":"carbon","name":"碳硅广场","status":"planned","eta":"2026-08-30"},
  ], "total": N}
```

## 4. 测试用例（6 条）

| # | 用例 | 断言 |
|---|------|------|
| 1 | 侧栏渲染 16 项 | 全部频道出现 |
| 2 | 已上线频道可点击 | 路由切换内容 |
| 3 | 规划中频道显示灰显占位 | 含"规划中"文案 |
| 4 | LLM 频道显示 providers | 数据加载 |
| 5 | 插件管理显示已装/未装 | 两类标记 |
| 6 | 不整页刷新 | hash 路由 |

## 5. 验收标准

| # | 维度 | 标准 |
|---|------|------|
| A | pytest | 新增 6 条全过 |
| B | ruff | 零新增 |
| C | 铁律2 | channels/status 返回信封 |
| D | 浏览器 | 16 项侧栏可点、规划中灰显、无死链 |
| E | 冒烟 | 登录→各频道切换无报错 |

## 6. 红线

1. 规划中频道不假装可用（灰显+文案）
2. 不引入新后端依赖（尽量前端完成）
3. 不显示具体客户名称
4. commit：`feat(saas-admin): 侧栏16频道补齐+规划中占位 [LLM: mimo-code]`
