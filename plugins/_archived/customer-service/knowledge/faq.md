# 常见问题 (FAQ)

## 产品相关

### Q: DDW AI 智能客服是什么？
A: DDW AI 智能客服是一款基于 RAG 技术的企业级知识库问答系统，可以帮助企业快速搭建专属的 AI 客服，支持云端和本地 LLM 部署。

### Q: 支持哪些 LLM 模型？
A: 我们支持多种 LLM 后端：
- **云端模型**：MiniMax (MiniMax-M3)、DeepSeek、OpenAI
- **本地模型**：Ollama、llama.cpp
您可以根据需求灵活选择。

### Q: 知识库支持哪些格式？
A: 支持 Markdown、YAML、TXT、JSON 等常见格式。推荐使用 Markdown 格式，便于编辑和维护。

### Q: 如何保证数据安全？
A: 所有数据存储在本地服务器，LLM 调用可选择本地模型（如 Ollama），数据完全不离开您的服务器，确保数据安全。

### Q: 200 次试用是什么意思？
A: 新用户可以免费试用 200 次对话，无需任何费用。试用期满后，只需支付 99 元即可永久使用，无任何后续费用。

### Q: 99 元是年费还是永久？
A: 99 元是一次性费用，永久使用，无任何年费或订阅费。

---

## 技术相关

### Q: 如何安装插件？
A: 有三种安装方式：
1. **插件市场**：在 DDW 平台插件市场搜索 "customer-service" 并安装
2. **手动下载**：从 GitHub 下载插件包并解压到 `plugins/` 目录
3. **命令行**：`ddw plugin install customer-service`

### Q: 如何配置知识库？
A: 将您的产品文档、FAQ 等放入 `plugins/customer-service/knowledge/` 目录即可。支持子目录，系统会自动扫描所有支持格式的文件。

### Q: 如何配置 LLM？
A: 编辑 `manifest.yaml` 文件中的 `llm` 部分：
```yaml
llm:
  provider: minimax  # 或 deepseek, openai, ollama, local
  api_key: "your-api-key"
  model: MiniMax-M3
```

### Q: 如何嵌入到我的网站？
A: 在网站 HTML 中添加以下代码：
```html
<script src="http://your-server:8500/api/v1/plugins/customer-service/widget"></script>
```
系统会自动在页面右下角显示聊天窗口。

### Q: 支持多语言吗？
A: 目前主要支持中文，LLM 模型本身支持多语言，您可以根据需要配置。

### Q: 如何查看对话历史？
A: 通过 API 接口 `/api/v1/plugins/customer-service/session/{session_id}/history` 可以查看指定会话的历史记录。

### Q: 如何限制访问频率？
A: 在 `manifest.yaml` 中配置 `chat.rate_limit` 参数，默认为每分钟 10 次请求。

---

## 商务相关

### Q: 如何购买正式版？
A: 试用期满后，系统会提示购买。您可以通过以下方式购买：
1. **在线支付**：访问 ddw-ai.com/pay
2. **联系销售**：发送邮件至 sales@ddw-ai.com
3. **社区购买**：在社区论坛联系管理员

### Q: 激活码如何获取？
A: 购买后会收到激活码，通过 API 接口 `/api/v1/plugins/customer-service/license/activate` 激活。

### Q: 有技术支持吗？
A: 有的。正式版用户享受：
- 邮件技术支持（24小时内响应）
- 社区论坛支持
- 文档和教程

### Q: 可以退款吗？
A: 购买后 7 天内，如未使用超过 50 次对话，可申请全额退款。

### Q: 企业批量购买有优惠吗？
A: 有的。10 套以上可享受 8 折优惠，50 套以上可享受 7 折优惠。请联系 sales@ddw-ai.com。

---

## 故障排除

### Q: AI 回答不准确怎么办？
A: 请检查：
1. 知识库内容是否准确和完整
2. 知识库文件格式是否正确
3. LLM 配置是否正确

### Q: 无法连接 LLM 怎么办？
A: 请检查：
1. API Key 是否正确
2. 网络连接是否正常
3. LLM 服务是否正常运行

### Q: 知识库加载失败怎么办？
A: 请检查：
1. 文件权限是否正确
2. 文件格式是否支持
3. 文件编码是否为 UTF-8

### Q: 响应速度慢怎么办？
A: 可以尝试：
1. 减小知识库大小
2. 调整分块大小（`knowledge.chunk_size`）
3. 使用更快的 LLM 后端
4. 增加服务器资源

---

**最后更新**：2026-07-12  
**版本**：1.0.0
