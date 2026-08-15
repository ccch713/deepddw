# DDW AI 智能客服插件 v2.0

<p align="center">
  <img src="https://img.shields.io/badge/version-2.0.0-blue.svg" alt="Version">
  <img src="https://img.shields.io/badge/license-commercial-green.svg" alt="License">
  <img src="https://img.shields.io/badge/python-3.8+-yellow.svg" alt="Python">
  <img src="https://img.shields.io/badge/DDW-0.1.0+-purple.svg" alt="DDW">
  <img src="https://img.shields.io/badge/规范-DDW_Plugin_v1.0-orange.svg" alt="规范">
</p>

<p align="center">
  <strong>基于 RAG 的企业智能客服解决方案</strong>
</p>

<p align="center">
  <a href="#功能特性">功能特性</a> •
  <a href="#快速开始">快速开始</a> •
  <a href="#插件开发规范">开发规范</a> •
  <a href="#定价">定价</a> •
  <a href="#文档">文档</a>
</p>

---

## 📋 功能特性

### 🤖 智能问答
- 基于 RAG 技术，精准回答客户问题
- 混合检索（向量 + 关键字 + 重排序）
- 支持多轮对话，理解上下文

### 🧠 意图识别
- 自动识别用户意图（产品咨询/价格咨询/技术支持/投诉等）
- 针对不同意图提供差异化回答

### 😊 情绪检测
- 检测用户情绪（正面/负面/愤怒）
- 自动调整回复语气

### 🔄 多轮对话
- Session + Context + 槽位管理
- 对话状态跟踪（initial → follow_up → completed）

### 👤 人工转接
- 自动检测转人工意图
- 投诉自动转人工

### 📚 知识库管理
- 支持 Markdown、YAML、TXT、JSON 等格式
- 智能分块和向量化
- 混合检索提高精度

---

## 🚀 快速开始

### 方式一：插件市场安装（推荐）

1. 登录 DDW 平台
2. 进入「插件市场」
3. 搜索「Customer Service」
4. 点击「安装」

### 方式二：手动安装

```bash
# 下载插件
git clone https://github.com/ddw-ai/customer-service-plugin.git

# 复制到插件目录
cp -r customer-service-plugin/plugins/customer-service /path/to/ddw-ai-hub/plugins/

# 重启 DDW 服务
ddw server restart
```

### 方式三：命令行安装

```bash
ddw plugin install customer-service
```

---

## 📐 插件开发规范

**本插件严格遵循 DDW AI 底座平台插件开发规范 v1.0**

### 核心原则

**插件必须复用平台已有能力，不要重复造轮子。**

### 平台已有能力（必须复用）

| 能力 | 说明 | 位置 |
|---|---|---|
| LLM Gateway | minimax 已配置 | config/deployment.yaml |
| 知识库加载器 | DDWKnowledgeBase | embedded_llm/engine.py |
| 插件基类 | PluginBase | sdk/plugin_base.py |
| 配置管理 | ConfigManager | sdk/config_manager.py |
| 工具定义 | ToolDefinition | sdk/tool_def.py |

### 本插件符合的规范

| 规范 | 状态 |
|---|---|
| ✅ 继承 PluginBase | 已实现 |
| ✅ 重写 setup() | 已实现 |
| ✅ 提供 register(app) | 已实现 |
| ✅ 使用 ConfigManager | 已实现 |
| ✅ 使用 self.router | 已实现 |
| ✅ 工具名以 ddw. 开头 | 已实现 |
| ✅ 描述 ≤250 字符 | 已实现 |

### 详细规范文档

完整的插件开发规范请参考：
- 项目内：`plugins/PLUGIN_DEVELOPMENT_RULES.md`
- Obsidian：`03_项目/DDW_AI底座平台/插件开发规范-v1.0.md`

---

## ⚙️ 配置说明

### 知识库配置

```yaml
config:
  knowledge:
    directory: "./knowledge"
    chunk_size: 500
    chunk_overlap: 50
```

### 对话配置

```yaml
config:
  chat:
    max_history: 20
    timeout: 30
    rate_limit: 10
```

### 许可证配置

```yaml
config:
  license:
    type: trial
    trial_limit: 200
    price: 99
```

---

## 💰 定价

| 版本 | 价格 | 额度 | 功能 |
|---|---|---|---|
| **试用版** | 免费 | 200 次对话 | 完整功能 |
| **正式版** | ¥99 | 无限制 | 完整功能 + 优先更新 |

---

## 📖 API 文档

### 发送消息
```
POST /api/v1/plugins/customer-service/chat
```

### 获取会话历史
```
GET /api/v1/plugins/customer-service/session/{session_id}/history
```

### 搜索知识库
```
GET /api/v1/plugins/customer-service/knowledge/search?q=关键词
```

### 获取许可证状态
```
GET /api/v1/plugins/customer-service/license/status
```

### 激活正式版
```
POST /api/v1/plugins/customer-service/license/activate?key=激活码
```

### 嵌入网站
```html
<script src="http://your-server:8500/api/v1/plugins/customer-service/widget"></script>
```

---

## 🏗️ 架构

```
customer-service/
├── __init__.py          # 插件主逻辑（继承 PluginBase）
├── manifest.yaml        # 插件配置
├── README.md            # 本文档
├── PLUGIN_DEV_RULES.md  # 开发规范
├── knowledge/           # 知识库
│   ├── RANGE_GUIDE.md
│   ├── products.md
│   └── faq.md
├── widget/
│   └── chat.html
└── dist/                # 打包产物
```

### 依赖关系

```
客服插件
    ↓
┌─────────────────────────────┐
│  DDW AI 底座平台             │
│  ├── PluginBase             │
│  ├── ConfigManager          │
│  ├── EmbeddedLLM            │
│  └── DDWKnowledgeBase       │
└─────────────────────────────┘
```

---

## ❓ 常见问题

### Q: 支持哪些 LLM？
A: 支持平台配置的所有 LLM（默认 minimax），也可使用本地模型。

### Q: 知识库大小有限制吗？
A: 没有硬性限制，但建议控制在 10MB 以内。

### Q: 如何保证数据安全？
A: 所有数据存储在本地，LLM 调用使用平台配置。

### Q: 200 次试用是什么意思？
A: 新用户可免费试用 200 次对话，之后 99 元永久使用。

---

## 📄 许可证

本项目采用商业许可证。

- **试用版**：免费，200 次对话
- **正式版**：¥99，永久使用

---

## 🙏 致谢

- [DDW AI Hub](https://github.com/ddw-ai/ddw-ai-hub) - 底座平台
- [MaxKB](https://github.com/1Panel-dev/MaxKB) - RAG 设计参考
- [Dify](https://github.com/langgenius/dify) - 混合检索参考
- [ChatWiki](https://github.com/zhimaAi/chatwiki) - 多格式支持参考

---

## 📞 联系我们

- **官网**：[ddw-ai.com](https://ddw-ai.com)
- **邮箱**：support@ddw-ai.com
- **GitHub**：[github.com/ddw-ai](https://github.com/ddw-ai)

---

<p align="center">
  Made with ❤️ by <a href="https://ddw-ai.com">DDW AI Team</a>
</p>
