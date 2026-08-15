# DDW 邮件整理及自动回复插件 — 决策门禁 ①

> 编译日期：2026-07-13
> 基于：Phase 1 市场调研 + Phase 2 竞品深度分析 + Phase 3 源码分析
> 参考报告：4份（共59.5KB），已同步至 Obsidian 知识库

---

## A. 市场调研结论（Phase 1）

| 维度 | 数据 | 评级 |
|:-----|:-----|:----:|
| GitHub 头部项目 | Inbox Zero 11,600+ Stars（全球第一） | 高 |
| GitHub 同类小项目 | 15+ 个（大部分 0 star） | 中 |
| 商业产品数量 | 7+ 个主流产品（Superhuman/Serif/Perplexity等） | 高 |
| 中国邮箱开源支持 | **0 个成熟方案**（仅 sse-email-mcp 提及QQ） | 空白 |
| 技术可行性 | IMAP/SMTP 通用标准，Python 标准库直接对接 | 已验证 |
| 热度评级 | **高（全球）/ 中国邮箱场景存在明确空白** | |

---

## B. 竞品分析结论（Phase 2）

### 2.1 Inbox Zero（最成熟竞品）

| 维度 | 数据 |
|:-----|:-----|
| Star/Fork | 11,600+ / 1,431 |
| 技术栈 | TypeScript/Next.js/Prisma/Google OAuth |
| 许可证 | **AGPL-3.0 + 商业附加条款**（5人以上组织需企业许可） |
| 核心功能 | AI规则引擎(16种Action)、批量退订、冷邮件拦截、邮件分析 |
| AI分类 | 三阶段pipeline：条件匹配 → 参数生成 → 动作执行 |
| **致命缺陷** | **不支持 IMAP/SMTP**（用户最高频需求，38 comments） |
| 仅支持 | Gmail（Google OAuth 绑定） |

**DDW 差异化机会**：Inbox Zero 最大痛点就是不支持 IMAP，DDW 插件天生支持所有邮箱。

### 2.2 MCP Email 生态

| 项目 | Star | 技术栈 | 中国邮箱 | 许可证 |
|:-----|:-----|:-------|:---------|:-------|
| ai-zerolab/mcp-email-server | 280 | Python/aioimaplib | 需手动配置 | MIT |
| codefuturist/email-mcp | 70 | TypeScript | 需手动配置 | - |
| marlinjai/email-mcp | 16 | TS/Gmail+Graph API | ❌ | - |
| 1018053166/sse-email-mcp-server | 4 | Python | **✅ 预配置QQ/163** | - |

**关键发现**：ai-zerolab 技术栈与 DDW 最匹配（Python+FastAPI）；sse-email-mcp 的中国邮箱预配置模式可直接借鉴。

### 2.3 inbox-autopilot（技术参考）

| 维度 | 数据 |
|:-----|:-----|
| Star | 0（2026-06 创建，新项目） |
| 技术栈 | TypeScript/Groq Llama 3.3/IMAP |
| 核心逻辑 | 极简：300 行 TypeScript，一次 LLM 调用完成分类+提取+草稿+告警 |
| 安全设计 | 邮件正文标记 untrusted、白名单校验 LLM 输出、IMAP 只读 |
| 许可证 | MIT |
| **可移植价值** | 高：triage prompt 设计 + IMAP 连接模式可直接参考 |

---

## C. 源码分析结论（Phase 3）

### 可复用的设计模式

| # | 来源 | 复用方式 | 说明 |
|:--|:-----|:---------|:-----|
| 1 | inbox-autopilot/triage.ts | 参考 Prompt 设计 | 一次 LLM 调用完成6项任务的高效 prompt |
| 2 | inbox-autopilot/imap.ts | 参考连接模式 | IMAP 只读+SSL+分页读取 |
| 3 | Inbox Zero ai-choose-rule | 仅思路借鉴 | 三阶段 rule engine 设计模式（AGPL不可复制代码） |
| 4 | sse-email-mcp/providers.json | 参考配置 | 中国邮箱 IMAP/SMTP 预配置表 |
| 5 | ai-zerolab 架构 | 参考分层 | Python+FastMCP+OS Keyring 安全存储 |
| 6 | codefuturist 分层 | 参考架构 | 47个MCP工具的分层组织方式 |

### 不可复制的代码

| 项目 | 许可证 | 原因 |
|:-----|:-------|:-----|
| Inbox Zero | AGPL-3.0 | 强传染性，使用其代码→DDW 也须 GPL 开源 |
| 其他项目 | MIT/Apache/无 | 可参考或直接复用 |

### DDW 实现方案（全新代码）

- **邮件收发层**：Python imaplib/smtplib（标准库，零依赖）+ 中国邮箱预配置表
- **AI 分类层**：MiniMax/DeepSeek API 调用，参考 inbox-autopilot 的 prompt 设计
- **规则引擎**：简化版三阶段（分类→草稿→动作），不需要 Inbox Zero 的 16 种 ActionType
- **安全层**：授权码加密存储(macOS keychain) + 邮件正文 untrusted 标记 + LLM 输出白名单校验

---

## D. ROI 量化评估

| 维度 | 评分(1-5) | 说明 |
|:-----|:---------:|:-----|
| **市场需求** | 4 | 全球高热度(11600+ Star标杆) + 中国邮箱空白 |
| **技术可行性** | 5 | IMAP/SMTP通用标准+Python标准库+LLM成本≈0 |
| **差异化空间** | 5 | 中国邮箱支持+草稿安全模式+DDW生态+零月费+MCP兼容 |
| **开发成本** | 4 | 参考项目多，核心逻辑≈500行Python，预估5-7天 |
| **维护成本** | 4 | IMAP/SMTP稳定协议+LLM API调用简单，低维护 |
| **商业价值** | 3 | 个人效率工具，直接收入有限，但验证DDW插件架构+引流 |
| **合计得分** | **25/30** | **≥20分 = 强烈推荐开发** |

---

## E. 开发成本估算

| 阶段 | 预估天数 | 说明 |
|:-----|:--------:|:-----|
| Phase 1 调研 | 1天 | ✅ 已完成 |
| Phase 2 竞品分析 | 1天 | ✅ 已完成（子Agent并行） |
| Phase 3 源码分析 | 0.5天 | ✅ 已完成 |
| Phase 4 决策门禁 | 0.5天 | 本次 |
| Phase 5 PRD | 1天 | 双LLM PRD |
| Phase 6 SDK开发 | 3-4天 | 核心~500行Python+测试+UI |
| Phase 7 测试 | 1天 | 单元+集成+安全 |
| Phase 8 打包部署 | 0.5天 | .ddwplugin打包+Gitea |
| **合计** | **7-8天** | 其中开发4-5天 |

---

## F. 资源消耗声明（预估）

| 维度 | 数据 |
|:-----|:-----|
| 代码体积 | ~500 行 Python（核心） + ~200 行前端 |
| 插件包大小 | < 100KB |
| 基础内存 | ~20 MB（FastAPI + SQLite） |
| 峰值内存 | ~50 MB（并发处理） |
| LLM 调用 | 每日 ~28,000 tokens（100封邮件） |
| LLM 月成本 | ~¥0.02（MiniMax Max 套餐内） |
| 外部依赖 | 无（Python 标准库 imaplib/smtplib） |
| 数据库存储 | SQLite ~1MB/月 |
| 资源评级 | **轻量级** ✅ |

---

## G. 投资回报预测

| 维度 | 数据 |
|:-----|:-----|
| 开发投入 | 5人天（核心开发） |
| 直接收入 | 无（开源免费插件） |
| 间接价值 | 1) 验证 DDW 个人效率插件架构 2) GitHub 引流 3) 社区口碑 4) 为后续收费插件铺路 |
| 风险成本 | 极低（5天开发，Python标准库，无外部付费依赖） |

---

## H. 核心风险

| 风险 | 概率 | 影响 | 缓解措施 |
|:-----|:----:|:----:|:---------|
| 邮箱授权码泄露 | 低 | 高 | macOS keychain加密存储，不明文落盘 |
| AI误判自动回复 | 中 | 高 | 默认"草稿模式"，需用户确认才发送 |
| 中国邮箱IMAP限制 | 低 | 中 | QQ/163已验证支持IMAP，企业邮箱需逐个测试 |
| 邮件格式解析复杂 | 中 | 中 | 优先处理plain text，HTML降级提取文本 |
| LLM回复质量不稳定 | 低 | 低 | 可切换Provider，用户可编辑草稿 |

---

## I. 开发建议

**值得开发：✅ 强烈推荐**

**核心理由**：
1. ROI 25/30，远超开发门槛(20分)
2. 技术难度低，Python标准库+IMAP即可，500行核心代码
3. 市场空白明确：无开源方案同时支持"中国邮箱+AI分类+草稿回复"
4. Inbox Zero 11600+ Star 验证了需求存在，但其 AGPL 许可证+不支持IMAP 给了 DDW 完整的差异化空间
5. 开发成本极低(5天)，风险极低，失败也可作为DDW插件架构的验证案例

**差异化定位**：
- **Inbox Zero** = Gmail + AGPL + 全自动
- **DDW Email Assistant** = 全邮箱(含中国) + Apache 2.0 + 草稿优先安全模式 + DDW生态

---

## J. 选项

A. **确认开发，按当前方向推进**（ROI ≥ 20分，进入 Phase 5 PRD）
B. 调整方向，返回 Phase 1 重新调研
C. 暂不开发，记录到 backlog

---

*决策报告编译完成时间：2026-07-13*
