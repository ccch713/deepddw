# TASK_SPEC：SaaS 管理后台侧栏 16 频道补齐（P1-4）

> 优先级：P1（Demo 后重点）
> 执行者：MiMo Code CLI（mimo run headless）
> 验收者：Hermes（DeepSeek 新标准 6 维验收）
> 关联 PRD：docs/PRD_P1_4_SaaS侧栏16频道.md
> 关联铁律：铁律1、铁律4（规划中频道灰显不假装可用）

---

## 一、背景与目标

saas-admin.html 侧栏仅 6 项，客户期望 16 项频道化呈现。本期只做**频道入口 + 频道页框架 + 已有数据展示 + 规划中灰显**，不引入新后端依赖。

## 二、侧栏频道清单（16 项）

| # | 频道 | 路由 | 数据源 | 状态 |
|---|------|------|--------|------|
| 1 | 数据概览 | #/overview | /admin/overview | ✅ 已有 |
| 2 | 成员管理 | #/users | /users/ | ✅ 已有 |
| 3 | LLM 配置 | #/llm | /llm/providers | 🟡 展示 |
| 4 | 知识库 | #/knowledge | 空态 | 🟡 占位 |
| 5 | 数字员工 | #/agents | 空态 | 🟡 规划中 |
| 6 | 技能 Skill | #/skills | 空态 | 🟡 规划中 |
| 7 | 碳硅广场 | #/carbon | 无 | ⚪ 规划中 v2.0 |
| 8 | DDW Pal | #/pal | 无 | ⚪ 规划中 v2.0 |
| 9 | 插件管理 | #/plugins | /admin/plugins | ✅ 已有 |
| 10 | 插件论坛 | #/forum | 空态 | 🟡 规划中 |
| 11 | 经销商 | #/partners | partner-directory | ✅ 已有 |
| 12 | 客户 Demo 账号 | #/demo-accounts | demo-accounts | ✅ 已有 |
| 13 | API Key | #/apikey | 已有 | ✅ |
| 14 | 套餐与账单 | #/billing | 已有 | ✅ |
| 15 | 发票管理 | #/invoices | 已有 | ✅ |
| 16 | 偏好设置 | #/preferences | 已有 | ✅ |

## 三、实现要点

### 3.1 侧栏结构（saas-admin.html 修改）

```html
<!-- 分组标题：总览 / AI 能力 / 企业管理 / 平台 -->
<div class="nav-group">
  <div class="nav-title">总览</div>
  <a class="nav-item" data-route="overview">数据概览</a>
</div>
<div class="nav-group">
  <div class="nav-title">AI 能力</div>
  <a class="nav-item" data-route="llm">LLM 配置 <span class="status-live">已上线</span></a>
  <a class="nav-item" data-route="knowledge">知识库 <span class="status-live">已上线</span></a>
  <a class="nav-item" data-route="agents">数字员工 <span class="status-plan">8/30</span></a>
  <a class="nav-item" data-route="skills">技能 Skill <span class="status-plan">8/30</span></a>
  <a class="nav-item" data-route="carbon">碳硅广场 <span class="status-plan">8/30</span></a>
  <a class="nav-item" data-route="pal">DDW Pal <span class="status-plan">8/30</span></a>
</div>
```

### 3.2 频道页通用框架

```html
<div class="channel-page" id="page-llm" style="display:none">
  <div class="channel-header">
    <h2>LLM 配置</h2>
    <span class="badge badge-on">已上线</span>
  </div>
  <div class="channel-body"><!-- 内容或规划中占位 --></div>
</div>
```

### 3.3 规划中占位

```html
<div class="empty-plan">
  <div class="icon">🚧</div>
  <h3>碳硅广场</h3>
  <p>该频道正在规划中，预计 8 月 30 日 v2.0 上线</p>
</div>
```

### 3.4 路由切换逻辑

```js
// hash 路由：显示对应 channel-page，隐藏其他
function showChannel(route) {
  document.querySelectorAll('.channel-page').forEach(p => p.style.display = 'none');
  const el = document.getElementById('page-' + route);
  if (el) el.style.display = 'block';
  // 高亮侧栏当前项
  document.querySelectorAll('.nav-item').forEach(x => x.classList.remove('active'));
  document.querySelector(`.nav-item[data-route="${route}"]`)?.classList.add('active');
}
```

## 四、测试用例（6 条）

| # | 用例 | 断言 |
|---|------|------|
| 1 | 侧栏渲染 16 项 | nav-item 数量 = 16 |
| 2 | 已上线频道可点击切换 | showChannel 生效 |
| 3 | 规划中频道显示灰显占位 | 含"规划中"文案 |
| 4 | LLM 频道加载 providers | 数据渲染 |
| 5 | 插件管理显示已装/未装 | 两类标记 |
| 6 | hash 路由不整页刷新 | location.hash 变化但页面不 reload |

## 五、验收标准

| # | 维度 | 标准 |
|---|------|------|
| A | 浏览器 | 16 项侧栏可点、规划中灰显、无死链 |
| B | 回归 | 原有 6 频道功能不破坏 |
| C | 铁律2 | 无新端点（如加 channels/status 需信封） |
| D | 冒烟 | 登录→各频道切换无报错 |

## 六、红线

1. 规划中频道不假装可用（灰显+文案）
2. 不引入新后端依赖（尽量纯前端）
3. 不显示具体客户名称
4. 沿用 saas-admin.html 现有 CSS 变量
5. commit：`feat(saas-admin): 侧栏16频道补齐+规划中占位 [LLM: mimo-code]`，不 push
6. 不要动 ECS 上的文件
