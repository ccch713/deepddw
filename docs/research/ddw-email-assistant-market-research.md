# Phase 1 市场调研报告：DDW 邮件整理及自动回复插件

> 调研日期：2026-07-13
> 调研人：Hermes Agent (MiMo V2.5 Pro)
> 插件暂定名：ddw-email-assistant

---

## 一、业务场景提炼

**核心痛点**：用户每天收到 ~100 封邮件，大量是 CC/通知类，真正需要手工敲字回复的仅 ~10 封。手动逐一打开、阅读、判断是否需要回复非常疲劳。

**目标用户**：个人用户 / 小型团队（非企业级 SaaS，而是个人 AI 效率工具）

**预期价值**：
1. AI 自动分类邮件（需要回复 / 知会 / 垃圾 / 订阅通知）
2. 对简单邮件自动生成草稿或自动回复
3. 只将需要深度思考的邮件推送给用户
4. 降低邮件处理时间 60-80%

**与 DDW 定位关系**：偏个人 AI 应用插件，作为 DDW 平台"个人效率"品类的首个插件，验证 DDW 插件架构对个人场景的支撑能力。

---

## 二、GitHub 搜索结果

### 2.1 头部项目（高 Star）

| # | 项目名 | Star | 最近更新 | 许可证 | 技术栈 | 与 DDW 相似度 |
|:--|:-------|:-----|:---------|:-------|:-------|:------------:|
| 1 | **elie222/inbox-zero** | 5,100+ | 2026-07-13 | 自定义(NOASSERTION) | TypeScript/Next.js | 中 |
| 2 | **marlinjai/email-mcp** | 新项目 | 活跃 | - | TypeScript | 高(协议层) |
| 3 | **ai-zerolab/mcp-email-server** | 新项目 | 活跃 | - | Python | 高(协议层) |
| 4 | **1018053166/sse-email-mcp-server** | 新项目 | 活跃 | - | Python | 高(QQ邮箱支持) |
| 5 | **Soundhannes/IMAP-MCP** | 新项目 | 活跃 | - | Python | 中(仅IMAP) |

### 2.2 个人级邮件 AI 项目（低 Star 但功能相关）

| # | 项目名 | Star | 技术栈 | 核心功能 |
|:--|:-------|:-----|:-------|:---------|
| 1 | jigangz/inbox-autopilot | 0⭐ | TS/Groq Llama | IMAP 分类+线索提取+草稿 |
| 2 | luffyzoro09/emailassistant | 0⭐ | Python/Ollama | IMAP扫描+本地LLM草稿 |
| 3 | killermasterturkey/smart-mail-assistant | 0⭐ | Python | NLP分类+摘要+智能回复 |
| 4 | zhouzhiouhub/Email_Bot | 0⭐ | Python | IMAP+LLM回复+知识库 |
| 5 | logan27335/mailflow-agent | 0⭐ | Python | IMAP分类+草稿回复 |

### 2.3 搜索结论

- **GitHub 上专门做"邮件 AI 分类+自动回复"的开源项目极少有高 Star**
- Inbox Zero 是唯一成功项目，但仅支持 Gmail（Google OAuth），不支持 IMAP 直连
- MCP email server 项目兴起但都是协议层工具，不是端到端产品
- **大量 0-Star 项目说明：需求真实存在，但没有成熟开源方案**

---

## 三、商业产品竞品分析

| 产品 | 类型 | 价格 | 邮箱支持 | AI 能力 | 定位 |
|:-----|:-----|:-----|:---------|:--------|:-----|
| **Superhuman** | 商业客户端 | $25+/月 | Gmail/Outlook | AI草稿/回复/分类 | 高端效率工具 |
| **Serif.ai** | SaaS | 付费 | Gmail/Outlook | Autopilot自动回复 | 企业邮件自动化 |
| **Perplexity Max** | AI搜索附加 | Max订阅 | Gmail/Outlook | AI邮件助手 | 搜索生态延伸 |
| **Gmail AI Inbox** | 原生功能 | 免费(付费增强) | 仅Gmail | Gemini分类/摘要 | Google生态 |
| **Outlook Copilot** | 原生功能 | M365订阅 | 仅Outlook | Copilot处理收件箱 | Microsoft生态 |
| **QQ邮箱 Agently Mail** | 新功能(内测) | 免费 | 仅QQ邮箱 | Agent收发邮件 | 腾讯生态 |
| **Mailr** | Chrome插件 | Free/$4.99月 | Gmail | AI写作/语气调整 | 轻量级写作辅助 |

### 商业产品关键洞察

1. **所有商业产品都绑定生态**（Gmail/Outlook/QQ邮箱），无跨邮箱通用方案
2. **价格门槛高**：Superhuman $25+/月，Perplexity Max 更贵
3. **中国市场空白**：Superhuman/Serif 不支持中国邮箱（QQ/163/企业邮箱）
4. **Agently Mail 刚内测**：腾讯方案，但绑定 QQ 邮箱生态
5. **没有"开源+自托管+中国邮箱支持"的方案**

---

## 四、全网热度判断

| 维度 | 数据 | 评级 |
|:-----|:-----|:-----|
| GitHub 头部项目 Star | Inbox Zero 5100+ | 高 |
| GitHub 同类小项目数量 | 15+ 个（大部分 0 star） | 中 |
| 知乎/CSDN 讨论 | 多篇深度文章，"AI邮件管理"搜索量上升 | 中高 |
| 商业产品数量 | 7+ 个主流产品 | 高 |
| 中国邮箱支持的开源方案 | **0 个**（仅 1018053166/sse-email-mcp-server 提及QQ） | 极低 |
| MCP email 协议工具 | 5+ 个（2025-2026 新兴） | 中 |
| **综合热度评级** | **高（全球）/ 中高（中国邮箱场景）** | |

---

## 五、技术可行性分析

### 5.1 邮件协议支持

| 邮箱 | IMAP 服务器 | SMTP 服务器 | 授权方式 | Himalaya 兼容 |
|:-----|:-----------|:-----------|:---------|:------------:|
| QQ邮箱 | imap.qq.com:993 | smtp.qq.com:465 | 授权码 | ✅ (有教程) |
| 163邮箱 | imap.163.com:993 | smtp.163.com:465 | 授权码 | ✅ (标准IMAP) |
| Gmail | imap.gmail.com:993 | smtp.gmail.com:465 | OAuth2/应用密码 | ✅ |
| Outlook/365 | outlook.office365.com:993 | smtp.office365.com:587 | OAuth2 | ✅ |
| 企业邮箱(腾讯) | imap.exmail.qq.com:993 | smtp.exmail.qq.com:465 | 客户端密码 | ✅ |
| 企业邮箱(阿里) | imap.qiye.aliyun.com:993 | smtp.qiye.aliyun.com:465 | 客户端密码 | ✅ |

**结论：IMAP/SMTP 协议是通用标准，所有主流中国邮箱都支持，技术无障碍。**

### 5.2 AI 处理流程设计

```
收件箱轮询（IMAP）
    ↓
邮件获取（header + body）
    ↓
AI 分类（LLM 调用）
  ├─ 需要回复（重要邮件）→ 生成草稿 → 推送给用户审核
  ├─ 简单确认类（可以自动回复）→ 生成回复 → 用户确认后发送
  ├─ 知会/通知类 → 自动标记已读 → 归档
  ├─ 订阅/营销类 → 建议退订 → 归档
  └─ 垃圾邮件 → 移入垃圾箱
    ↓
用户审核面板（Web UI）
  ├─ 待处理队列（需要回复的邮件）
  ├─ 自动生成的回复草稿
  └─ 一键确认/编辑/跳过
```

### 5.3 LLM 成本估算

| 场景 | 每封邮件 token 消耗 | 每日 100 封 | 月成本(MiniMax Max) |
|:-----|:-------------------|:-----------|:-------------------|
| 分类判断 | ~200 tokens | 20,000 | ~¥0.01 |
| 草稿生成(10封) | ~500 tokens | 5,000 | ~¥0.003 |
| 自动回复(简单) | ~300 tokens | 3,000 | ~¥0.002 |
| **合计** | - | **28,000** | **~¥0.015/月** |

**结论：LLM 成本几乎可以忽略不计，使用 MiniMax Max 套餐绰绰有余。**

### 5.4 技术栈选型

| 组件 | 方案 | 理由 |
|:-----|:-----|:-----|
| 邮件收发 | Python imaplib/smtplib | 标准库，零依赖，比 Himalaya 更轻量（Himalaya 是 Rust CLI，集成需 subprocess） |
| AI 分类 | MiniMax API / DeepSeek API | DDW 已有 Provider 层，直接复用 |
| 数据存储 | SQLite | 个人插件，无需 PostgreSQL |
| Web UI | DDW 前端框架 | 复用 DDW 管理面板 |
| 定时任务 | APScheduler / DDW cron | 定期轮询收件箱 |

---

## 六、初步结论

### 6.1 值得开发：✅ 是

**理由**：
1. **需求真实且高频**：每天 100 封邮件 → 痛点明确，ROI 直观
2. **市场空白**：无开源方案同时支持"中国邮箱 + AI 分类 + 自动回复"
3. **技术无障碍**：IMAP/SMTP 通用标准 + LLM 成本极低
4. **DDW 插件架构验证**：作为个人效率插件，验证 DDW 对非企业场景的适配
5. **差异化明确**：
   - 开源 + 自托管（隐私安全）
   - 支持中国邮箱（QQ/163/企业邮箱）
   - DDW 生态内，可与其他插件组合（如知识库插件、权限插件）
   - 一次性部署，无月费

### 6.2 核心风险

| 风险 | 等级 | 缓解措施 |
|:-----|:----:|:---------|
| 邮箱授权码安全 | 高 | 加密存储(keychain)，不明文落盘 |
| AI 误判自动回复 | 高 | 默认"草稿模式"，需用户确认才发送 |
| 中国邮箱 IMAP 限制 | 中 | 已验证 QQ/163 支持 IMAP |
| 邮件格式解析 | 中 | 多格式支持(plain/html/mixed) |
| LLM 回复质量 | 低 | 可切换 Provider，可本地 LLM |

### 6.3 差异化卖点

1. **唯一支持中国邮箱的开源 AI 邮件助手**（QQ/163/企业邮箱）
2. **DDW 插件生态第一个个人效率插件**（vs 全是企业级插件）
3. **"草稿优先"安全模式**（vs Inbox Zero 的全自动模式）
4. **零月费**（用自有 LLM API / 本地 LLM）
5. **MCP 兼容**（可与其他 MCP 工具组合使用）

---

## 七、下一步建议

按照 DDW 插件开发流程，Phase 1 调研完成，建议进入 Phase 2（竞品深度研究），重点深入研究：

1. **Inbox Zero**（最成熟竞品）—— 分析其 AI 分类规则引擎、Google OAuth 集成方式
2. **email-mcp** 系列 —— 分析 MCP 邮件协议的实现模式
3. **jigangz/inbox-autopilot** —— 唯一使用 Groq+IMAP 的项目，技术栈最接近

然后进入决策门禁 ①。

---

*报告完成时间：2026-07-13*
