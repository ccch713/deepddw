# DDW 问渠学生端工作台 TASK_SPEC v1.0（Pal 学生版 · WorkBuddy 式三段式）

> **状态**：待开发（学科包已交付 bb7a217，本规格可直接投喂）
> **日期**：2026-08-05
> **作者**：Hermes Agent（DeepSeek-V4-Flash）
> **形态**：独立静态前端（PWA 化），复用 Pal 的 WorkBuddy 三段式交互范式（**不修改 ddw-pal 标准版**）
> **部署**：/opt/wenqu/frontend/（问渠独立目录，Caddy 静态托管）

---

## 0. 业务规则（用户拍板）

1. **学生端 = WorkBuddy 式三段式工作台**（用户 2026-08-05 发怒定调：禁 CLI + 演示页形态，交付默认 GUI 可操作）
2. 左=课程/章节（学科包对接）、中=对话（模式切换+快捷指令）、右=成果文档区（错题本/学习报告真渲染）
3. 对接服务：`ddw_wenqu_tutor`（12 API）+ `ddw_wallet`（余额/充值）
4. 计费透明：开课前显示预计费用；余额不足 → 充值弹窗（微信 Native 二维码）
5. 独立实现前端（不 import ddw-pal 代码），DDW 插件后端零修改

## 1. 目录结构

```
frontend/（问渠仓库内，部署 /opt/wenqu/frontend/）
├── student.html          # 学生端三段式工作台（单文件，含全部 CSS/JS）
├── login.html            # 学生登录页（简易：学生名+学科选择，V1 无复杂鉴权）
├── assets/
│   ├── favicon.png       # 问渠 Logo（朱砂圆印 A 版）
│   └── manifest.webmanifest  # PWA manifest（后续）
└── README.md
```

V1 为单文件 `student.html`（内嵌 CSS+JS，遵循 DDW 零构建静态前端惯例），后续再拆分。

## 2. 布局规格（三段式，1440×900 基准）

```
┌──────────┬──────────────────────────┬──────────────────┐
│ 左栏 240px│ 中栏（弹性）              │ 右栏 360px        │
│ ┌────────┐│ ┌──────────────────────┐ │ ┌──────────────┐ │
│ │ 学生身份││ │ 头部：学科切换 + 模式   │ │ │ 成果区 Tab   │ │
│ │ 头像/名 ││ │ 切换 + 余额显示        │ │ │ ①错题本      │ │
│ ├────────┤│ ├──────────────────────┤ │ │ ②学习报告    │ │
│ │ 课程树  ││ │ 对话区（气泡流式）     │ │ │ ③周报预览    │ │
│ │ 物理    ││ │ · 用户右/教练左+打字机 │ │ │ （markdown   │ │
│ │ ├─声现象││ │ · 旁白*斜体*渲染      │ │ │  真渲染）    │ │
│ │ ├─欧姆  ││ ├──────────────────────┤ │ └──────────────┘ │
│ │ 化学    ││ │ 输入框 + 快捷指令 chips│ │                  │
│ │ ├─分子  ││ │ （错题复盘/真题/下课） │ │                  │
│ │ └───────┘│ └──────────────────────┘ │                  │
└──────────┴──────────────────────────┴──────────────────┘
```

### 2.1 左栏（240px）
- 顶部：学生头像（问渠 Logo 圆形）+ 学生名（默认 CXY）+ 余额（xx 元，点击弹充值窗）
- 课程树：学科（物理/化学）→ 章节列表（学科包 `/textbook/list`），点击章节 → 中栏开课
- 底部：下课/结束按钮

### 2.2 中栏
- 头部：当前学科徽章 + 模式切换（**苏格拉底课 / 真题演练 / 错题复盘**）+ 预计费用提示（如"预计 0.2 元/分钟"）
- 对话区：
  - 气泡：用户右（蓝/朱砂色）、教练左（白底+头像）
  - 流式渲染（SSE/fetch stream），打字机效果
  - 旁白 `*...*` 斜体灰色渲染；LaTeX `$...$` 不渲染（V1 原样显示，V1.1 引入 KaTeX）
  - 下课按钮（学习者主动触发，遵守下课铁律）
- 快捷指令 chips：`错题复盘` `来道真题` `今天学了啥` `下课`
- 输入框：Enter 发送、Shift+Enter 换行；发送时显示"教练思考中..."

### 2.3 右栏（360px，成果文档区）
- Tab ① **错题本**：列表卡片（题目摘要/错误类型徽章/知识点），点击 → 中栏触发复盘
- Tab ② **学习报告**：markdown 真渲染（课程完成总结，来自学科包）
- Tab ③ **周报预览**：家长周报样式（时长/错题分布/弱项雷达条形图，纯 CSS 实现）

## 3. API 对接

```javascript
// 基础 URL：同源代理（Caddy 反代 /api → 后端）
const API = "/api/v1/plugins";
const TUTOR = `${API}/ddw_wenqu_tutor`;
const WALLET = `${API}/ddw_wallet`;

// 1. 开课
POST ${TUTOR}/session/start  {student_name, subject, chapter}
→ 402 → 弹充值窗（调钱包 /recharges 创建 → 显示二维码）

// 2. 对话（流式）
POST ${TUTOR}/session/{id}/message  {content}
→ SSE/fetch-stream 逐段渲染

// 3. 下课（结算）
POST ${TUTOR}/session/{id}/end
→ {active_minutes, charge_cents, balance_after_cents} → 右栏刷新余额 + 报告

// 4. 错题本
GET ${TUTOR}/wrongbook/list?resolved=false
POST ${TUTOR}/wrongbook/{id}/redo  → 返回复盘会话 → 中栏切换

// 5. 真题
GET ${TUTOR}/questions/list?subject=&chapter=&difficulty=
POST ${TUTOR}/questions/submit {question_id, student_answer, session_id}

// 6. 钱包
GET ${WALLET}/accounts/{user_id}
POST ${WALLET}/recharges {amount_cents:500, channel:"wechat", user_id}
→ pay_params.code_url → QRCode 渲染（qrcode.js CDN 或本地实现）

// 7. 家长统计（右栏 Tab③）
GET ${TUTOR}/parent/stats?student_name=&days=7
```

**错误处理**：402（余额不足）→ 全屏充值引导；网络错误 → 重试按钮 + 提示"教练走神了，点一下继续"；会话进行中意外断连 → 本地缓存消息，重连后继续。

## 4. 视觉规范（新中式三色 + 问渠品牌）

- 主色：朱砂 `#B03A2E`（按钮/徽章/教练头像环）、宣纸 `#F7F1E3`（背景）、墨 `#3A3A3A`（正文）、金 `#E8C46B`（强调/余额）
- 字体：PingFang SC（中文），楷体用于 Logo 区
- Logo：问渠朱砂圆印（assets/favicon.png）
- 深色模式：V1.1 再评估（三色主题切换遵循 localStorage `ddw-palette` 惯例——V1 只做宣纸默认色）

## 5. 测试与验收

```bash
# 1. JS 语法检查
node --check <extracted js>          # 提取 student.html 内 script 验证

# 2. headless Chrome 渲染验证（DDW 惯例）
chrome --headless --dump-dom student.html
→ 断言：三段式容器存在、课程树渲染、模式切换按钮、余额区
chrome --headless --screenshot → 视觉检查（mmx vision describe）

# 3. Mock API 联调
本地起简易 mock server（返回固定 JSON）→ 走通：开课→对话→下课→错题→报告

# 4. 真实 API 联调（等部署后）
/opt/wenqu 后端 + 本前端 → 苏格拉底对话真机走通
```

**验收标准**：
1. headless DOM：三段式布局 + 关键元素断言通过
2. 交互走通（mock）：开课 → 对话流式 → 下课结算 → 余额刷新 → 错题复盘 → 真题提交
3. 402 充值流程：mock 余额不足 → 充值窗出现 → 二维码渲染
4. 视觉检查：无乱版、中文渲染正常、Logo 正确
5. node --check 零错误

## 6. 开发顺序（MiMo Code，AHE Loop）

1. **M0**：student.html 骨架（三段式布局 + 三色 CSS + 空交互）→ headless DOM 验证
2. **M1**：API 对接层（fetch 封装 + 错误处理 + 余额显示）
3. **M2**：对话流（流式渲染 + 打字机 + 快捷指令 + 下课结算）
4. **M3**：右栏三 Tab（错题本/报告 markdown 渲染/周报预览）
5. **M4**：充值窗（二维码）+ login.html + assets + README → 全量验证

**约束**：
- 禁止修改 plugins/ 下任何后端代码（前端纯对接）
- JS 用原生 ES2020（零构建，无 npm 依赖；二维码可用内嵌 qrcode 生成函数或本地 js 文件）
- 所有 API 调用带 try/catch；所有金额显示单位为元（分/100）
- 中文文案亲切（"教练""加油"），禁机械感
