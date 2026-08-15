# TASK_SPEC: DDW Pal（默认首登界面 + Skill 创建入口）

> 优先级：P0  
> 预计工时：3-5 天  
> 状态：待确认  
> 前身：ddw-code-cli（08-05 更名为 DDW Pal）

---

## 1. 概述

DDW Pal 是 DDW 所有用户登录后的**默认界面**。它是员工日常工作的 AI 窗口，提供：
- AI 对话（接入 LLM 网关）
- Skill 创建/编辑（YAML 编辑器）
- 数据分析（调用知识库/数字员工）
- 可嵌入泛微 OA

**核心定位**：DDW Pal = 员工的 AI 工作台 = "你每天打开 DDW 第一眼看到的东西"

## 2. 页面结构

```
┌─────────────────────────────────────────────────────┐
│  DDW Pal                              万永刚 ···998165 │
├──────────┬──────────────────────────────────────────┤
│          │                                          │
│  对话    │   🤖 DDW Pal 你好！我是你的 AI 工作助手。  │
│  ├─ 新建 │                                          │
│  ├─ 历史 │   用户：帮我分析一下上个月的销售数据        │
│  │       │                                          │
│  Skill   │   🤖 好的，我来调用数据录入员（数录）的     │
│  ├─ 我的 │      数据分析 skill...                     │
│  ├─ 创建 │                                          │
│          │   ┌──────────────────────────────┐        │
│  数字员工 │   │ [输入框]              [发送] │        │
│  ├─ 笑笑 │   └──────────────────────────────┘        │
│  ├─ 法海 │                                          │
│  ├─ ...  │                                          │
│          │                                          │
├──────────┴──────────────────────────────────────────┤
│  © 2026 武汉锐果互动 | 鄂ICP备2026024883号-1        │
└─────────────────────────────────────────────────────┘
```

## 3. 功能模块

### 3.1 AI 对话

- 多轮对话，底部固定输入框
- 接入 LLM 网关（自动路由到可用 provider）
- 支持 Skill 调用（用户说"帮我查知识库"→自动路由到 ddw.kb.search）
- 对话历史保存（本地 + 服务端）
- 支持附件上传（图片/PDF → 对应 vision/pdf skill）

### 3.2 Skill 创建

- 左侧"Skill → 创建"入口
- YAML 编辑器（monospace textarea + 语法高亮）
- 预设模板：对话型 / 工具型 / 数据型 / 集成型
- 保存 → 写入 skill_definitions 表
- 测试运行 → 在当前对话中测试 skill

### 3.3 数字员工快捷入口

- 左侧"数字员工"列表（从 AI 组织模块读取）
- 点击数字员工 → 直接进入与该数字员工的对话
- 显示数字员工状态（在线/忙碌/离线）

### 3.4 泛微 OA 嵌入

- DDW Pal 提供独立 URL：`/ddw-pal.html`
- 可通过 iframe 嵌入泛微 OA
- 嵌入时隐藏 DDW 导航栏（`?embed=true` 参数）
- 泛微 OA 内通过 postMessage 传递认证信息

## 4. API 端点

```yaml
# 对话
POST   /api/v1/pal/chat                            # 发送消息（含 skill 路由）
GET    /api/v1/pal/history                         # 对话历史
DELETE /api/v1/pal/history                         # 清空历史

# Skill 创建
POST   /api/v1/pal/skills                          # 创建 skill（YAML）
PUT    /api/v1/pal/skills/{id}                     # 修改 skill
GET    /api/v1/pal/skills                          # 我的 skill 列表
POST   /api/v1/pal/skills/{id}/test                # 测试运行 skill

# 数字员工
GET    /api/v1/pal/agents                          # 可用数字员工列表（含状态）
POST   /api/v1/pal/agents/{id}/chat                # 与指定数字员工对话
```

## 5. 前端实现

### 5.1 页面文件

- `frontend/ddw-pal.html` — DDW Pal 主页面
- 纯 HTML + CSS（DDW 主题变量）+ 原生 JS
- 不依赖 React/Vue，保持与 saas-admin 一致的技术栈

### 5.2 登录后跳转

```javascript
// login.html 登录成功后
var landing = '/saas-admin.html#pal';  // 默认：DDW Pal
if (role === 'admin' || role === 'superadmin') {
  landing = '/admin.html';
} else if (role === 'partner') {
  landing = '/partner-demo-accounts.html';
}
```

### 5.3 泛微嵌入

```html
<!-- 泛微 OA 内嵌入 -->
<iframe src="https://ddw.9cio.com/ddw-pal.html?embed=true" 
        style="width:100%;height:600px;border:none"></iframe>

<script>
// 泛微侧传递认证
document.querySelector('iframe').contentWindow.postMessage({
  type: 'ddw-auth',
  token: 'xxx',
  user: { name: '万永刚', phone: '18571998165' }
}, 'https://ddw.9cio.com');
</script>
```

## 6. 验收标准

| # | 验证项 | 预期结果 |
|---|--------|----------|
| 1 | 登录后默认页 | 进入 DDW Pal（非 saas-admin 仪表盘） |
| 2 | AI 对话 | 发送消息 → LLM 回复 |
| 3 | Skill 创建 | YAML 编辑 → 保存 → 出现在"我的 Skill"列表 |
| 4 | 数字员工入口 | 左侧显示 11 个数字员工（从 AI 组织读取） |
| 5 | 泛微嵌入 | iframe 加载正常，?embed=true 隐藏导航 |

## 7. 依赖

- LLM 网关（TASK_SPEC_TOKEN_PLAZA）需就绪
- AI 组织（TASK_SPEC_AI_ORG）需就绪（数字员工列表）
- Skill 池（TASK_SPEC_SKILL_POOL）需就绪
