# 口腔门诊 AI 赋能系统 · 视觉设计规范

> 来源：`商务物料/口腔诊所AI赋能方案_v1_20260805.html`
> 用户确认：后续该项目所有前端界面均采用此配色和纹理

---

## 一、Design Tokens（CSS 变量）

```css
:root {
  /* === 品牌色 === */
  --brand:        #0B6E99;   /* 主色：医疗蓝（信赖感、专业感） */
  --brand-dark:   #08547A;   /* 深蓝：标题、强调 */
  --brand-light:  #E8F4FA;   /* 浅蓝：徽章背景、步骤圆圈 */

  /* === 强调色 === */
  --accent:       #F08A24;   /* 暖橙：CTA 按钮、重点标注 */

  /* === 背景 === */
  --bg:           #FFFFFF;   /* 纯白主背景 */
  --bg-soft:      #F6FAFD;   /* 微蓝灰：交替区块背景 */

  /* === 文字 === */
  --text:         #24313C;   /* 主文字：深灰蓝 */
  --text-secondary: #5A6B7A; /* 辅助文字：中灰 */

  /* === 边框 === */
  --border:       #E3EDF4;   /* 卡片边框、分割线 */

  /* === 状态 === */
  --success:      #2E9E6B;   /* 成功/勾选绿 */
}
```

## 二、配色语义对照

| 语义 | Token | 色值 | 使用场景 |
|:--|:--|:--|:--|
| 品牌主色 | `--brand` | `#0B6E99` | 导航栏、标签文字、编号数字 |
| 深色强调 | `--brand-dark` | `#08547A` | 卡片标题（h3/h4）、Hero 渐变终止色 |
| 浅色背景 | `--brand-light` | `#E8F4FA` | 徽章底色、步骤圆圈底色、表头背景 |
| CTA 强调 | `--accent` | `#F08A24` | 按钮、价格标注、重点数字 |
| 页面背景 | `--bg` | `#FFFFFF` | body |
| 区块背景 | `--bg-soft` | `#F6FAFD` | section-alt（交替区块） |
| 主文字 | `--text` | `#24313C` | 正文、列表项 |
| 辅助文字 | `--text-secondary` | `#5A6B7A` | 描述、注释、小字 |
| 边框 | `--border` | `#E3EDF4` | 卡片 border、分割线 dashed |
| 成功 | `--success` | `#2E9E6B` | ✓ 图标、"可独立启动"标签 |

## 三、渐变纹理（Hero / AI 亮点 / CTA）

```
Hero 背景：linear-gradient(135deg, #0B6E99 0%, #0A5C84 55%, #08547A 100%)
AI 卡片：  linear-gradient(160deg, #0B6E99 0%, #0A5C84 100%)
CTA 区块：  linear-gradient(135deg, #0B6E99 0%, #08547A 100%)
```

**装饰圆（Hero 右上角）**：
```css
.hero::after {
  content: "";
  position: absolute;
  right: -120px; top: -120px;
  width: 380px; height: 380px;
  border-radius: 50%;
  background: rgba(255,255,255,0.06);
}
```

## 四、组件规范

### 卡片（.card / .pain / .cap / .step）
```css
background: #fff;
border: 1px solid var(--border);
border-radius: 12-14px;
padding: 22-28px;
box-shadow: 0 3px 14px rgba(11,110,153,0.05);
transition: transform .15s ease, box-shadow .15s ease;
```
**Hover 效果**：
```css
transform: translateY(-3px);
box-shadow: 0 6px 18px rgba(11,110,153,0.08);
```

### CTA 按钮
```css
background: var(--accent);           /* #F08A24 暖橙 */
color: #fff;
font-size: 16px; font-weight: 600;
padding: 14px 40px;
border-radius: 30px;
box-shadow: 0 6px 18px rgba(240,138,36,0.35);
transition: transform .15s ease;
```
**Hover**：`transform: translateY(-2px);`

### 步骤圆圈（.step-no）
```css
width: 40px; height: 40px;
border-radius: 50%;
background: var(--brand-light);    /* #E8F4FA */
color: var(--brand);               /* #0B6E99 */
font-weight: 700; font-size: 17px;
```

### 编号标签（.num）
```css
color: var(--brand);
font-weight: 700; font-size: 13px;
letter-spacing: 1px;
```

### 徽章（.badge）
```css
font-size: 12px; font-weight: 600;
padding: 3px 10px; border-radius: 12px;
/* 蓝色版 */ background: var(--brand-light); color: var(--brand);
/* 橙色版 */ background: #FEF0E0; color: var(--accent);
```

### 成功标签（.indep）
```css
font-size: 12px; color: var(--success);
background: #EAF6EF;
padding: 3px 10px; border-radius: 12px;
```

## 五、排版规范

| 元素 | 字号 | 行高 | 字重 |
|:--|:--|:--|:--|
| Hero h1 | 40px（桌面）/ 30px（手机） | 1.3 | 700 |
| Section h2 | 30px | — | — |
| Card h3/h4 | 16-19px | — | — |
| 正文 | 14-17px | 1.75 | 400 |
| 辅助文字 | 13-14px | — | 400 |
| 标签 (tag) | 13px | — | 600 |

**字体栈**：
```
-apple-system, "PingFang SC", "Microsoft YaHei", "Helvetica Neue", sans-serif
```

## 六、响应式断点

```css
@media (max-width: 900px) {
  /* 网格列从3列→1列 */
  .pains, .caps, .ais, .steps { grid-template-columns: 1fr; }
  .dual { grid-template-columns: 1fr; }
  .hero h1 { font-size: 30px; }
  .hero { padding: 52px 0 46px; }
}
```

## 七、与锐果/DDW 主站设计系统的关系

| 维度 | DDW 主站 (ruiguo-ddw-design-system) | 口腔项目 (本文件) |
|:--|:--|:--|
| CSS 变量 | ✅ 必须用 `var(--xxx)` | ✅ 一致 |
| Tailwind 颜色类名 | ❌ 禁止 | ❌ 禁止 |
| 硬编码 hex | ❌ 禁止 | ❌ 禁止 |
| 品牌色 | `#0B6E99` | `#0B6E99`（一致） |
| CTA 橙 | `#F08A24` | `#F08A24`（一致） |

**结论**：口腔项目的配色与 DDW 主站完全兼容，可以共用 `base.css` 的结构变量，口腔项目只需覆盖 `--brand` / `--accent` 等色值。
