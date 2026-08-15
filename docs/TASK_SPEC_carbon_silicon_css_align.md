# TASK_SPEC: carbon-silicon.html CSS 变量统一对齐

> **日期**：2026-08-11
> **目标**：将 carbon-silicon.html 的 CSS 变量体系和视觉风格对齐到 saas-admin.html
> **开发工具**：MiMo Code CLI

---

## 1. 现状

- carbon-silicon.html 只有 6 个 CSS 变量（`--brand`, `--bg`, `--card`, `--border`, `--text`, `--muted`）
- saas-admin.html 有 25+ 个 CSS 变量（`--bg-base`, `--bg-card`, `--text-primary`, `--brand` 等）
- 大量色值硬编码：`#555`, `#666`, `#f0f0f0`, `#fafafa`, `#fafbfc`, `#e5484d`, `#16a34a` 等

## 2. 对齐方案

### 2.1 替换 `:root` 块

将 carbon-silicon.html 的 `:root` 替换为 saas-admin.html 的完整变量集：

```css
:root {
  --bg-base: #F0F2F5;
  --bg-card: #FFFFFF;
  --bg-elevated: #FAFAFA;
  --bg-hover: #F5F7FA;
  --bg-sidebar: #001529;
  --text-primary: #333333;
  --text-secondary: #666666;
  --text-muted: #999999;
  --text-placeholder: #BBBBBB;
  --text-inverse: #FFFFFF;
  --brand: #1890FF;
  --brand-hover: #40A9FF;
  --brand-light: #E6F4FF;
  --border: #E8E8E8;
  --border-light: #F0F0F0;
  --border-input: #D9D9D9;
  --border-focus: #1890FF;
  --success: #52C41A;
  --success-bg: #F6FFED;
  --success-border: #B7EB8F;
  --warning: #FAAD14;
  --warning-bg: #FFFBE6;
  --warning-border: #FFE58F;
  --danger: #F5222D;
  --danger-bg: #FFF1F0;
  --danger-border: #FFA39E;
  --info: #1890FF;
  --info-bg: #E6F7FF;
  --info-border: #91D5FF;
  --shadow-dropdown: 0 8px 24px rgba(0,0,0,0.12);
}
```

### 2.2 全局替换映射

| 旧值（硬编码/旧变量） | 新值 |
|:----------------------|:-----|
| `var(--bg)` | `var(--bg-base)` |
| `var(--card)` | `var(--bg-card)` |
| `var(--text)` | `var(--text-primary)` |
| `var(--muted)` | `var(--text-muted)` |
| `var(--border)` | `var(--border)` （保持不变） |
| `var(--brand)` | `var(--brand)` （保持不变） |
| `#555` | `var(--text-secondary)` |
| `#666` | `var(--text-secondary)` |
| `#6b7280` | `var(--text-muted)` |
| `#f0f0f0` | `var(--border-light)` |
| `#fafafa` | `var(--bg-elevated)` |
| `#fafbfc` | `var(--bg-base)` |
| `#e5484d` | `var(--danger)` |
| `#16a34a` | `var(--success)` |
| `#f0fdf4` | `var(--success-bg)` |
| `#fffbeb` | `var(--warning-bg)` |
| `#d97706` | `var(--warning)` |
| `#fef2f2` | `var(--danger-bg)` |
| `#e6f4ff` | `var(--brand-light)` |
| `#f3f4f6` | `var(--bg-hover)` |

### 2.3 视觉对齐

- 顶栏高度、字体大小与 saas-admin 保持一致
- 卡片圆角统一 8px
- 按钮样式统一（padding/border-radius/font-size）
- 表格样式统一

## 3. 验收标准

- [ ] `grep -c '#[0-9A-Fa-f]\{3,6\}' carbon-silicon.html` 在 `style="..."` 内联中为 0
- [ ] `:root` 变量数 ≥ 25
- [ ] 页面渲染效果与 saas-admin 视觉风格一致
- [ ] 无 JS 错误

## 4. 禁止事项

- 禁止修改页面的功能逻辑（DAG 编辑器、流程列表等）
- 禁止删除已有功能
- 禁止引入新依赖
