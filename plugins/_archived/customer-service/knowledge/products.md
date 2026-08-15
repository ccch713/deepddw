# 示例产品介绍

## DDW AI 智能客服

### 产品概述
DDW AI 智能客服是一款基于 RAG 技术的企业级知识库问答系统，帮助企业快速搭建专属的 AI 客服。

### 核心功能

#### 1. 多格式知识库支持
- 支持 Markdown、YAML、TXT、JSON 等格式
- 自动分块和索引
- 智能检索相关知识

#### 2. 多 LLM 后端
- **云端模型**：MiniMax、DeepSeek、OpenAI
- **本地模型**：Ollama、llama.cpp
- 灵活配置，按需选择

#### 3. 对话管理
- 多轮对话支持
- 会话历史记录
- 上下文理解

#### 4. 易于集成
- RESTful API
- 可嵌入任何网站
- 响应式设计

### 适用场景

#### 企业官网客服
- 7x24 小时在线
- 快速响应客户咨询
- 减少人工客服压力

#### 产品技术支持
- 技术问题自动解答
- 常见问题 FAQ
- 文档智能检索

#### 售前咨询
- 产品功能介绍
- 服务范围说明
- 价格咨询

### 技术优势

#### 1. RAG 技术
- 基于知识库的精准回答
- 减少 AI 幻觉
- 可追溯信息来源

#### 2. 灵活部署
- 支持云端和本地部署
- 数据完全可控
- 满足不同安全需求

#### 3. 高性价比
- 200 次免费试用
- 99 元永久使用
- 支持多种 LLM 后端

### 快速开始

#### 1. 安装插件
```bash
# 在 DDW 平台插件市场搜索 "customer-service"
# 或手动下载插件包并解压到 plugins 目录
```

#### 2. 配置知识库
```bash
# 将产品文档放入 knowledge 目录
cp your-product-docs.md plugins/customer-service/knowledge/
```

#### 3. 配置 LLM
```yaml
# 修改 manifest.yaml 中的 LLM 配置
llm:
  provider: minimax
  api_key: "your-api-key"
  model: MiniMax-M3
```

#### 4. 启动服务
```bash
ddw server start
```

#### 5. 嵌入网站
```html
<!-- 在网站中添加以下代码 -->
<script src="http://your-server:8500/api/v1/plugins/customer-service/widget"></script>
```

### 常见问题

#### Q: 支持哪些 LLM？
A: 支持 MiniMax、DeepSeek、OpenAI 等云端模型，以及 Ollama、llama.cpp 等本地模型。

#### Q: 知识库大小有限制吗？
A: 没有硬性限制，但建议控制在 10MB 以内以保证检索速度。

#### Q: 如何保证数据安全？
A: 所有数据存储在本地，LLM 调用可选择本地模型，完全不离开您的服务器。

#### Q: 技术支持如何获取？
A: 请访问 support@ddw-ai.com 或加入我们的社区。

---

**版本**：1.0.0  
**更新日期**：2026-07-12  
**许可证**：商业许可（200次试用 / 99元永久）
