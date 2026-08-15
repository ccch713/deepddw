# PRD: DDW Email Assistant Plugin v1.0.0

> 版本：1.0.0
> 日期：2026-07-13
> 定位：企业级邮件整理与自动回复插件（DDW AI 底座平台）
> 许可证：Apache 2.0（开源引流）

---

## 一、产品概述

### 1.1 产品定位

DDW 邮件助手是 DDW AI 底座平台的**企业级邮件自动化插件**，通过 AI 智能分类、草稿生成、自动回复，帮助企业和团队大幅降低邮件处理负担。

**不是**个人邮件工具（与 OpenClaw/WorkBuddy 不竞争个人市场）。
**而是**企业级邮件自动化方案（数据不出内网、权限控制、审计日志）。

### 1.2 核心价值主张

1. **企业数据安全**：自托管部署，邮件数据不出企业内网
2. **权限控制 + 审计日志**：基于 DDW 权限引擎，每封自动回复可追溯
3. **无厂商锁定**：Apache 2.0 开源，可自由修改和部署

### 1.3 目标用户

- 企业 IT 管理员（部署和配置）
- 企业员工（日常使用）
- DDW 平台研究者（二次开发）

---

## 二、功能需求

### 2.1 核心功能

| 功能 | 优先级 | 说明 |
|:-----|:------:|:-----|
| 邮箱账户管理 | P0 | 支持 IMAP/SMTP 多账户配置 |
| AI 邮件分类 | P0 | 自动将邮件分为：需要回复/知会/垃圾/订阅 |
| 草稿生成 | P0 | 对需要回复的邮件自动生成回复草稿 |
| 自动回复(需确认) | P0 | 简单邮件自动生成回复，用户确认后发送 |
| 邮件归档 | P1 | 自动归档已处理邮件 |
| 批量退订 | P1 | 识别订阅邮件并批量退订 |
| 中文邮箱支持 | P0 | QQ/163/企业邮箱预配置 |
| Web 管理面板 | P0 | 邮箱配置、规则管理、待处理队列 |
| 审计日志 | P1 | 记录每封自动回复的操作日志 |

### 2.2 用户故事

**作为企业员工**，我希望：
- 每天打开邮件面板，看到 AI 已经帮我分类好的邮件
- 简单邮件已经有回复草稿，我只需点"确认发送"
- 重要邮件被高亮提醒，不会被淹没

**作为企业 IT 管理员**，我希望：
- 一键配置员工邮箱账户（IMAP/SMTP）
- 查看所有自动回复的审计日志
- 控制哪些邮件可以自动回复，哪些必须人工处理

### 2.3 邮件分类规则

| 分类 | 判断标准 | 处理方式 |
|:-----|:---------|:---------|
| **需要回复** | 直接发给我、有明确问题、等待回复 | 生成草稿 → 推送用户 |
| **简单确认类** | 确认收到/同意/已阅 | 生成回复草稿 → 用户确认后发送 |
| **知会/通知** | CC、系统通知、公告 | 自动标记已读 → 归档 |
| **订阅/营销** | Newsletter、推广邮件 | 建议退订 → 归档 |
| **垃圾邮件** | 广告、钓鱼、可疑 | 移入垃圾箱 |

---

## 三、技术设计

### 3.1 技术栈

| 组件 | 选型 | 理由 |
|:-----|:-----|:-----|
| 邮件收发 | Python imaplib/smtplib | 标准库，零依赖 |
| AI 分类 | MiniMax/DeepSeek API | DDW 已有 Provider 层 |
| 数据存储 | SQLite | 个人/小团队，无需 PostgreSQL |
| Web 框架 | FastAPI | DDW 插件标准 |
| 前端 | HTML/CSS/JS | 复用 DDW 管理面板风格 |
| 定时任务 | APScheduler | 定期轮询收件箱 |

### 3.2 目录结构

```
ddw-email-assistant/
├── manifest.yaml          # 插件元数据
├── __init__.py            # 桥接入口
├── main.py                # 插件主类（继承 PluginBase）
├── router.py              # FastAPI 路由
├── models.py              # SQLAlchemy ORM 模型
├── services/
│   ├── __init__.py
│   ├── email_service.py   # IMAP/SMTP 邮件操作
│   ├── ai_service.py      # AI 分类和草稿生成
│   ├── account_service.py # 邮箱账户管理
│   └── audit_service.py   # 审计日志
├── providers/
│   ├── __init__.py
│   ├── base.py            # 邮箱提供商基类
│   ├── qq_mail.py         # QQ 邮箱适配
│   ├── netease_163.py     # 163 邮箱适配
│   ├── tencent_exmail.py  # 腾讯企业邮适配
│   ├── alibaba_exmail.py  # 阿里企业邮适配
│   └── generic_imap.py    # 通用 IMAP 适配
├── templates/
│   ├── index.html         # 主页面
│   └── settings.html      # 设置页面
├── static/
│   ├── css/style.css
│   └── js/app.js
├── requirements.txt
├── tests/
│   ├── __init__.py
│   ├── test_email_service.py
│   ├── test_ai_service.py
│   └── test_providers.py
├── README.md
└── LICENSE                # Apache 2.0
```

### 3.3 数据模型

```python
# models.py

class EmailAccount(Base):
    """邮箱账户"""
    id: int              # 主键
    name: str            # 账户名称（如"工作邮箱"）
    email: str           # 邮箱地址
    provider: str        # 提供商类型(qq/163/exmail/generic)
    imap_host: str       # IMAP 服务器
    imap_port: int       # IMAP 端口
    smtp_host: str       # SMTP 服务器
    smtp_port: int       # SMTP 端口
    auth_type: str       # 认证方式(password/authorization_code)
    encrypted_creds: str # 加密存储的凭证
    is_active: bool      # 是否启用
    created_at: datetime
    updated_at: datetime

class EmailMessage(Base):
    """邮件消息"""
    id: int
    account_id: int      # 关联账户
    message_id: str      # 邮件 Message-ID
    subject: str         # 主题
    sender: str          # 发件人
    recipients: str      # 收件人(JSON)
    cc: str              # 抄送(JSON)
    body_text: str       # 纯文本内容
    body_html: str       # HTML 内容
    received_at: datetime
    classification: str  # 分类结果(need_reply/simple/info/spam/junk)
    confidence: float    # 分类置信度
    auto_reply_draft: str # 自动生成的回复草稿
    status: str          # 状态(pending/drafted/replied/archived)
    created_at: datetime

class AuditLog(Base):
    """审计日志"""
    id: int
    account_id: int
    message_id: int
    action: str          # 操作(classify/draft/reply/archive/delete)
    details: str         # 操作详情(JSON)
    operator: str        # 操作者(system/user)
    created_at: datetime
```

### 3.4 API 端点

| 方法 | 路径 | 说明 |
|:-----|:-----|:-----|
| GET | /api/email/accounts | 获取所有邮箱账户 |
| POST | /api/email/accounts | 添加邮箱账户 |
| PUT | /api/email/accounts/{id} | 更新邮箱账户 |
| DELETE | /api/email/accounts/{id} | 删除邮箱账户 |
| POST | /api/email/accounts/{id}/test | 测试邮箱连接 |
| GET | /api/email/messages | 获取邮件列表(分页+筛选) |
| GET | /api/email/messages/{id} | 获取邮件详情 |
| POST | /api/email/messages/{id}/classify | 手动重新分类 |
| POST | /api/email/messages/{id}/draft | 生成回复草稿 |
| POST | /api/email/messages/{id}/reply | 发送回复(确认后) |
| POST | /api/email/messages/{id}/archive | 归档邮件 |
| POST | /api/email/sync/{account_id} | 手动同步邮件 |
| GET | /api/email/stats | 邮件统计信息 |
| GET | /api/email/audit | 审计日志查询 |

### 3.5 AI 分类 Prompt 设计

```
你是一个邮件分类助手。请根据以下邮件信息进行分类。

邮件信息：
- 主题：{subject}
- 发件人：{sender}
- 收件人：{recipients}
- 抄送：{cc}
- 内容摘要：{body_summary}

请将邮件分类为以下之一：
1. need_reply - 需要回复（直接发给我的、有明确问题、等待回复）
2. simple_confirm - 简单确认类（确认收到/同意/已阅，可以用模板回复）
3. info_only - 知会/通知（CC、系统通知、公告，只需知晓）
4. newsletter - 订阅/营销（Newsletter、推广邮件）
5. spam - 垃圾邮件（广告、钓鱼、可疑）

请返回 JSON 格式：
{
  "classification": "分类结果",
  "confidence": 0.95,
  "reason": "分类理由",
  "suggested_action": "建议操作"
}
```

### 3.6 AI 草稿生成 Prompt 设计

```
你是一个邮件回复助手。请根据以下邮件内容生成一封专业、简洁的回复草稿。

邮件信息：
- 主题：{subject}
- 发件人：{sender}
- 内容：{body}

要求：
1. 语气专业、友好
2. 回复简洁，不超过原文长度的 1/3
3. 如果是简单确认类，使用标准确认模板
4. 如果是需要回复的，针对问题给出具体回应
5. 使用中文回复（如果原文是中文）

请直接输出回复内容，不需要额外说明。
```

---

## 四、中国邮箱预配置

### 4.1 邮箱提供商配置表

| 提供商 | IMAP 服务器 | IMAP 端口 | SMTP 服务器 | SMTP 端口 | 认证方式 |
|:-------|:-----------|:---------|:-----------|:---------|:---------|
| QQ 邮箱 | imap.qq.com | 993 | smtp.qq.com | 465 | 授权码 |
| 163 邮箱 | imap.163.com | 993 | smtp.163.com | 465 | 授权码 |
| 126 邮箱 | imap.126.com | 993 | smtp.126.com | 465 | 授权码 |
| 腾讯企业邮 | imap.exmail.qq.com | 993 | smtp.exmail.qq.com | 465 | 客户端密码 |
| 阿里企业邮 | imap.qiye.aliyun.com | 993 | smtp.qiye.aliyun.com | 465 | 客户端密码 |
| 网易企业邮 | imap.qiye.163.com | 993 | smtp.qiye.163.com | 993 | 客户端密码 |
| Gmail | imap.gmail.com | 993 | smtp.gmail.com | 465 | OAuth2/应用密码 |
| Outlook | outlook.office365.com | 993 | smtp.office365.com | 587 | OAuth2 |

### 4.2 授权码获取引导

配置向导中必须包含：
1. 各邮箱的"开启 IMAP 服务"步骤截图
2. 授权码生成步骤说明
3. 常见错误提示（如"授权码错误"、"IMAP 未开启"）

---

## 五、安全设计

### 5.1 凭证存储

- 授权码使用 AES-256 加密后存储在 SQLite
- 加密密钥从环境变量 `DDW_EMAIL_SECRET_KEY` 读取
- 不在日志中打印任何凭证信息
- 不在 Web 界面明文显示授权码

### 5.2 邮件安全

- 邮件正文标记为 untrusted data，不直接执行其中的任何内容
- AI 回复草稿经过白名单校验（只允许纯文本/HTML，不允许注入脚本）
- 自动回复默认关闭，需用户手动开启
- 回复前必须经过用户确认（草稿模式）

### 5.3 审计追踪

- 每次 AI 分类操作记录日志
- 每次草稿生成记录日志
- 每次自动回复记录日志（含发送内容）
- 审计日志不可删除，保留 90 天

---

## 六、资源消耗声明

| 维度 | 数据 |
|:-----|:-----|
| 代码体积 | ~800 行 Python（核心） + ~300 行前端 |
| 插件包大小 | < 150KB |
| 基础内存 | ~25 MB |
| 峰值内存 | ~60 MB |
| LLM 调用 | 每日 ~28,000 tokens（100封邮件） |
| LLM 月成本 | ~¥0.02（MiniMax Max 套餐内） |
| 外部依赖 | 无（Python 标准库 imaplib/smtplib） |
| 数据库存储 | SQLite ~1MB/月 |
| 资源评级 | **轻量级** ✅ |

---

## 七、开发计划

| 阶段 | 天数 | 内容 |
|:-----|:----:|:-----|
| Phase 5 PRD | 1天 | ✅ 本次完成 |
| Phase 6 SDK 开发 | 3天 | 核心功能实现 |
| Phase 7 测试 | 1天 | 单元+集成+安全 |
| Phase 8 打包 | 0.5天 | .ddwplugin + Gitea |
| GitHub 文案 | 0.5天 | README + 官网文案（需用户确认） |
| **合计** | **6天** | |

---

*PRD 完成时间：2026-07-13*
