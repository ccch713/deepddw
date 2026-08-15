# TASK_SPEC：P0-2 右上角用户信息显示 + P0-3 Demo页面侧栏 + P0-4 LLM双轨

> 紧急程度：P0（客户 Demo 前必须完成）
> 执行者：MiMo Code CLI（mimo run headless）
> 验收者：Hermes（DeepSeek 新标准 6 维验收）
> 关联铁律：铁律1（冒烟）、铁律2（API契约）

---

## 一、背景

2026-08-10 用户反馈三个 UI 问题：
1. **P0-2**：登录后右上角不显示用户姓名和账户（手机后六位），显示"未登录"假象
2. **P0-3**：客户 Demo 账号页面（partner-demo-accounts.html）点击后侧栏消失，像另一个未完成产品
3. **P0-4**：数据概览 LLM 网关卡片没有"云端/自建"双轨标识，客户会问"模型是哪家的？数据安全吗"

---

## 二、实现方案

### 2.1 P0-2 右上角用户信息（frontend/saas-admin.html）

**现状**：saas-admin.html 头部 userChip 区域显示"未登录"或空白
**改法**：
```
1. 页面加载时调 GET /api/v1/auth/me（后端已存在，返回 user_id/phone/name/role/tenant_id）
2. 右上角显示：{name} · {phone后6位}  + 角色徽章（owner=管理员/成员）
3. localStorage 缓存 me 数据，避免每次刷新都调
4. 显示格式：万永刚 · 998165
```

### 2.2 P0-3 客户 Demo 账号页面侧栏（frontend/partner-demo-accounts.html）

**现状**：partner-demo-accounts.html 是独立页面，没有复用 admin.html 侧栏
**改法**：
```
方案A（推荐）：在 partner-demo-accounts.html 中复制 admin.html 侧栏结构 + 高亮当前项
方案B：改为 iframe 嵌入 admin.html
选 A：加 <aside class="sidebar"> 同样的导航，当前项高亮"客户Demo账号"
```

### 2.3 P0-4 LLM 网关双轨（frontend/saas-admin.html 数据概览）

**现状**：LLM 网关卡片只显示调用次数/tokens/成本
**改法**：
```
1. 卡片顶部加 Provider 双轨 tag：
   云端：{provider名称列表}（如 MiniMax/DeepSeek/火山方舟）
   自建：{本地模型列表}（如 Qwen3/Llama，走 Ollama）
2. 每种轨道显示：
   云端：token 数量 × 官方单价 = 预估支出费用
   自建：token 数量 × 原厂云端单价 = 预估节约费用
3. 数据来源：GET /api/v1/admin/llm/usage（需确认返回结构，若缺 provider 分类则后端补充）
```

**后端补充**（如 usage 端点缺字段）：
```python
# core/api/admin.py 或 llm.py
GET /api/v1/admin/llm/usage
→ {
  "cloud": {"tokens": N, "cost_cny": X.XX, "providers": ["MiniMax","DeepSeek"]},
  "selfhosted": {"tokens": N, "saved_cny": X.XX, "providers": ["Qwen3"]}
}
```

---

## 三、测试用例（5 条）

| # | 用例 | 断言 |
|---|------|------|
| 1 | GET /auth/me 返回 name/phone | name 非空 |
| 2 | saas-admin.html 右上角渲染用户信息 | 含"万永刚"或登录用户 name |
| 3 | partner-demo-accounts.html 有侧栏 | sidebar 元素存在 |
| 4 | GET /admin/llm/usage 返回 cloud/selfhosted 双轨 | 两个 key 都在 |
| 5 | LLM 卡片显示双轨 tag | 含"云端"和"自建"字样 |

## 四、验收标准（DeepSeek 新标准）

| # | 维度 | 标准 |
|---|------|------|
| A | pytest | 新增 5 条测试全过，全量回归无破坏 |
| B | ruff | 零新增 error |
| C | 铁律2 | usage 端点返回裸对象（单对象类型），不违反契约 |
| D | 浏览器 | 右上角显示用户名+手机尾号；demo页有侧栏；LLM卡片有双轨 |
| E | 冒烟 | 登录→概览→demo账号页 无死链 |

## 五、红线

1. 不显示完整手机号（只后6位）
2. 不硬编码客户名称（万永刚只是测试数据）
3. 前端 CSS 沿用 saas-admin.html 现有变量
4. commit：`feat(ui): 右上角用户信息+Demo页侧栏+LLM双轨 [LLM: mimo-code]`，不 push
