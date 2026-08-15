# 问渠学生端工作台

DDW 问渠学生端 — AI 教练苏格拉底式学习工作台。

## 文件结构

```
frontend/wenqu/
├── student.html      # 学生端三段式工作台（单文件，内嵌 CSS/JS）
├── login.html        # 学生登录页
├── assets/
│   └── favicon.png   # 问渠 Logo（朱砂圆印）
└── README.md
```

## 布局

三段式工作台（1440×900 基准）：

- **左栏 240px**：学生身份 + 课程树（物理/化学章节）
- **中栏（弹性）**：对话区（流式气泡）+ 模式切换 + 快捷指令
- **右栏 360px**：错题本 / 学习报告 / 周报预览

## 视觉规范

- 朱砂 `#B03A2E`（按钮/徽章/教练头像环）
- 宣纸 `#F7F1E3`（背景）
- 墨 `#3A3A3A`（正文）
- 金 `#E8C46B`（强调/余额）

## API 对接

对接两个后端插件：

- `ddw_wenqu_tutor`（12 API）— 课程/对话/错题/报告
- `ddw_wallet`（余额/充值）— 微信 Native 二维码

## 技术栈

- 纯静态 HTML + 内嵌 CSS/JS
- 原生 ES2020，零构建零 npm 依赖
- 内嵌 QR Code 生成器（无 CDN 依赖）
- PWA-ready（manifest.webmanifest 待后续添加）

## 部署

部署至 `/opt/wenqu/frontend/`，Caddy 静态托管。

## 开发

本地预览：

```bash
# 用任意静态服务器
python3 -m http.server 8080 -d frontend/wenqu/
# 或
npx serve frontend/wenqu/
```

联调需配置 Caddy 反代 `/api` → 后端服务。
