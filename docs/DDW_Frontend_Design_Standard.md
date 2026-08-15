# DDW AI Hub 前端设计规范

> **版本**：v1.0（2026-08-01）
> **适用范围**：DDW AI Hub 所有前端页面（管理后台、插件市场、AI助手、知识库、数字员工）
> **设计锚点**：Ant Design 企业 OA 风格（泛微E9/E10 + 蓝凌MK + 帆软FineBI）

---

## 一、设计原则

1. **企业工具审美**：不是"好看的网站"，是"好用的工具"。功能优先，装饰克制。
2. **Ant Design 对齐**：颜色、间距、组件形态与 Ant Design 保持一致，降低企业用户学习成本。
3. **去 AI 化**：禁止渐变背景、emoji 图标、玻璃拟态、装饰性阴影。用 flat 设计 + SVG 图标。
4. **嵌入优先**：所有页面可通过 iframe 嵌入泛微OA/蓝凌MK/钉钉工作台/飞书工作台。

---

## 二、色彩系统

### 2.1 主色板（Ant Design 标准）

| Token | 色值 | 用途 |
|-------|------|------|
| `--c-primary` | `#1890FF` | 主色：按钮、链接、选中态、进度条 |
| `--c-primary-hover` | `#40A9FF` | 主色 hover |
| `--c-primary-bg` | `#E6F7FF` | 主色浅底：选中行、标签背景 |
| `--c-success` | `#52C41A` | 成功：在线、完成、正常 |
| `--c-warning` | `#FAAD14` | 警告：延迟、异常、管理员标签 |
| `--c-error` | `#FF4D4F` | 错误：断开、离线、危险操作 |

### 2.2 中性色

| Token | 色值 | 用途 |
|-------|------|------|
| `--c-text` | `#333333` | 主文字 |
| `--c-text-2` | `#666666` | 次要文字 |
| `--c-text-3` | `#999999` | 辅助文字、占位符 |
| `--c-border` | `#D9D9D9` | 边框 |
| `--c-bg` | `#F0F2F5` | 页面背景 |
| `--c-white` | `#FFFFFF` | 卡片/面板背景 |

### 2.3 深色区域

| 区域 | 色值 | 说明 |
|------|------|------|
| 顶部导航栏 | `#001529` | 泛微/蓝凌标准深蓝黑 |
| 侧边栏 | `#001529` | Ant Design Pro 暗色侧栏 |
| AI 头像 | `#001529` | 对话中 AI 方头像 |

### 2.4 禁止使用的颜色

- 渐变背景（linear-gradient / radial-gradient）
- 玻璃拟态（backdrop-filter: blur）
- 装饰性阴影（box-shadow 用于非焦点状态）
- 金色/橙色作为主色（DDW 品牌色 #E8B86D 仅用于 Logo 强调，不用于按钮/链接）

---

## 三、排版规范

### 3.1 字体

```css
--font: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
--mono: "SF Mono", Menlo, Consolas, monospace;
```

### 3.2 字号层级

| 元素 | 字号 | 字重 | 用途 |
|------|------|------|------|
| 页面标题 | 18px | 600 | `.page-title` |
| 卡片标题 | 14px | 500 | `.card-head .title` |
| 正文 | 14px | 400 | body 默认 |
| 辅助文字 | 13px | 400 | 描述、meta 信息 |
| 标签/徽章 | 12px | 400 | `.tag` |
| 最小文字 | 11px | 400 | 时间戳、脚注 |
| 等宽数据 | 12-14px | 400 | `font-family: var(--mono)` |

### 3.3 行高

- 正文：1.5715（Ant Design 默认）
- 紧凑列表：1.5

---

## 四、间距与圆角

### 4.1 间距

| 场景 | 值 |
|------|-----|
| 页面内容区 padding | 16px 24px |
| 卡片内 padding | 16px |
| 卡片间距 | 12px |
| 表格单元格 padding | 10px 12px |
| 统计卡片间距 | 12px |

### 4.2 圆角

- 所有组件：`border-radius: 2px`（Ant Design 标准）
- Tag/徽章：`border-radius: 2px`
- 禁止 >4px 的圆角

---

## 五、组件规范

### 5.1 按钮

| 类型 | 高度 | padding | 样式 |
|------|------|---------|------|
| 默认 | 32px | 0 12px | 白底 + #D9D9D9 边框 |
| 主要 | 32px | 0 12px | #1890FF 底 + 白字 |
| 小号 | 28px | 0 8px | 同上缩小 |
| 大号 | 40px | 0 20px | 同上放大 |

### 5.2 标签（Tag）

```css
.tag { 
  display: inline-block; padding: 0 6px; height: 20px; 
  line-height: 20px; border-radius: 2px; font-size: 12px; border: 1px solid; 
}
.tag-blue { color: #1890FF; border-color: #91D5FF; background: #E6F7FF; }
.tag-green { color: #52C41A; border-color: #B7EB8F; background: #F6FFED; }
.tag-orange { color: #FAAD14; border-color: #FFD591; background: #FFFBE6; }
.tag-red { color: #FF4D4F; border-color: #FFA39E; background: #FFF2F0; }
.tag-default { color: #999; border-color: #D9D9D9; background: #FAFAFA; }
```

### 5.3 表格

- 表头背景：`#FAFAFA`
- 行 hover：`#FAFAFA`
- 分隔线：`1px solid #F0F0F0`
- 禁止斑马纹

### 5.4 卡片

```css
.card { 
  background: #FFFFFF; border: 1px solid #D9D9D9; 
  border-radius: 2px; margin-bottom: 12px; 
}
```

- 禁止 box-shadow
- 禁止 hover 上浮效果
- hover 变化：仅边框色变为 `#1890FF`

### 5.5 状态点（Dot）

```css
.dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; margin-right: 6px; }
.dot-green { background: #52C41A; }
.dot-orange { background: #FAAD14; }
.dot-gray { background: #D9D9D9; }
```

---

## 六、页面布局

### 6.1 整体结构

```
┌─────────────────────────────────────────────┐
│  顶部导航栏 #001529（48px 高）               │
│  [Logo] [工作台] [插件市场] [文档]    [帮助]  │
├────────┬────────────────────────────────────┤
│        │                                    │
│  侧边栏 │          内容区                     │
│  #001529│   面包屑 → 页面标题 → 统计卡片      │
│  208px  │          → 功能区域                 │
│        │                                    │
├────────┴────────────────────────────────────┤
```

### 6.2 侧边栏菜单

- 分组：用 `.menu-label`（11px，大写，半透明白字）
- 选中态：`background: #1890FF` + `border-right: 2px solid #1890FF`
- 图标：SVG（14×14px），stroke 风格

### 6.3 响应式断点

| 断点 | 侧边栏 | 布局 |
|------|--------|------|
| ≥1200px | 208px 完整 | 标准布局 |
| 960-1199px | 48px 图标 | 内容区自适应 |
| <960px | 隐藏 | 移动端适配 |

---

## 七、AI 助手页面规范

### 7.1 三段式布局

```
┌──────────┬──────────────────────┬──────────────┐
│ 左栏 200px │      中栏 flex        │  右栏 300px   │
│          │                      │              │
│ AI 插件   │    对话消息区          │   AI 产物     │
│ 选择器    │                      │   列表面板    │
│          │                      │              │
│          │                      │              │
│          ├──────────────────────┤              │
│          │   输入区（textarea）   │              │
│          │   发送按钮（80px宽）   │              │
└──────────┴──────────────────────┴──────────────┘
```

### 7.2 输入区规范

- **textarea 最小高度**：44px（2 行）
- **textarea 最大高度**：120px（可拉伸）
- **发送按钮**：高度 44px，宽度 80px，`#1890FF` 底色
- **提示文字**：11px，`#999`，"支持文件上传 · 知识库检索 · 多轮对话"

### 7.3 产物面板

- 背景：`#FAFAFA`（浅灰区分）
- 产物卡片：白底 + 1px 边框 + hover 边框变蓝
- 显示：类型标签（10px 等宽）+ 名称 + 信息 + 预览片段

### 7.4 嵌入模式

AI 助手页面支持通过 iframe 嵌入企业现有系统：

```html
<!-- 泛微OA / 蓝凌MK / 钉钉工作台 / 飞书工作台 -->
<iframe 
  src="https://ddw-ai.com/chat?token=SSO_TOKEN&platform=weaver" 
  style="width:100%;height:100vh;border:none;"
  allow="microphone">
</iframe>
```

嵌入时：
- 隐藏顶部导航栏（通过 URL 参数 `?embed=1` 控制）
- 保留侧边栏（可折叠）
- SSO Token 由企业系统通过 URL 参数传递

---

## 八、插件市场页面规范

### 8.1 布局

- 搜索栏 + 分类筛选按钮（胶囊形）
- 卡片网格（`grid-template-columns: repeat(auto-fill, minmax(260px, 1fr))`）
- 每张卡片：名称 + 状态标签 + 描述 + meta 信息（端点数/测试数/分类）

### 8.2 卡片交互

- hover：边框色变为 `#1890FF`
- 禁止 hover 上浮、阴影变化

---

## 九、知识库页面规范（待设计）

### 9.1 多级知识库体系

| 知识库 | 权限 | 说明 |
|--------|------|------|
| 企业公共知识库 | 全员 | 企业文化、制度、通知 |
| 客服知识库 ×N | 客服团队 | 产品FAQ、话术、案例 |
| 财务知识库 | 财务部 | 报表模板、税务规则（非公开） |
| 研发知识库 | 研发部 | 技术文档、API、架构 |
| 采购知识库 | 采购部 | 供应商、合同、价格 |
| 高层决策库 | 管理层 | 战略、竞品、市场分析 |
| 岗位知识库 | 按岗位 | SOP、操作手册、培训材料 |
| 设备知识库 | 设备部 | 设备手册、维护记录 |

### 9.2 页面布局（待定）

- 左侧：知识库树形导航（按组织架构分组）
- 中间：文档列表 + 搜索
- 右侧：文档预览 / AI 问答

---

## 十、数字员工页面规范（待设计）

### 10.1 功能模块

| 模块 | 说明 |
|------|------|
| 岗位列表 | 所有数字员工卡片视图 |
| 岗位详情 | 岗位名称、职责描述、技能配置 |
| 工作流编辑 | DAG 可视化编排（SOP 引擎联动） |
| 交付物标准 | 每个岗位的输出格式和质量要求 |
| 定时任务 | cron 调度配置 |
| 运行日志 | 执行记录、耗时、成功率 |

### 10.2 页面布局（待定）

- 左侧：岗位列表
- 中间：岗位详情 / 工作流编辑器
- 右侧：运行日志 / 交付物预览

---

## 十、去 AI 化检查清单

所有前端页面交付前必须通过：

```
[ ] 无 emoji 图标（用 SVG 或文字首字母）
[ ] 无渐变背景（flat color）
[ ] 无 box-shadow 装饰
[ ] 无 AI-slop 高频词（赋能/助力/一站式/打造/闭环）
[ ] 无虚构数据（标注 [演示数据] 或用真实数据）
[ ] 圆角 ≤ 2px
[ ] 边框 1px solid #D9D9D9
[ ] 颜色使用 Ant Design 标准色板
[ ] 按钮/标签高度符合规范
[ ] iframe 嵌入可用（顶部导航可隐藏）
```

---

## 十一、关联文档

| 文档 | 路径 |
|------|------|
| 本规范 | `docs/DDW_Frontend_Design_Standard.md` |
| 前端架构策划 | `docs/DDW_Frontend_UI_Architecture_Plan.md` |
| 插件开发指南 | `docs/DDW_Plugin_Development_Guide.md` |
| 去AI化 Skill | `~/.hermes/skills/creative/html-deai-pipeline/SKILL.md` |
| Demo v5 | `frontend/DDW_Platform_Demo_v5.html` |
