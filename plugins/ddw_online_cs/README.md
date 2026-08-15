# 锐果互动官网客服知识库

## 客服模块概述

锐果互动在线 AI 客服系统「果果」是基于 DDW AI 底座平台构建的智能客服解决方案，集成 RAG（检索增强生成）知识库 + MiniMax-M3 大语言模型，为客户提供 7×24 小时在线咨询服务。

### 核心技术架构

- **前端**：全站浮动对话框（右下角），支持打字机逐字显示效果，表情包自然表达
- **后端**：FastAPI + RAG 知识库检索 + MiniMax-M3 云端 LLM（国内直连）
- **知识库**：纯 stdlib 实现的混合检索（md5 哈希桶向量 + 关键词），支持多文件扩展
- **部署**：DDW AI Hub 插件架构（`plugins/ddw_online_cs/`），标准 plugin.py 协议

### 功能特性

| 特性 | 说明 |
|:--|:--|
| 售前引导（官网 www.9cio.com） | 回答产品/服务问题，引导行业/规模/痛点，激发购买意向 |
| 售后支持（DDW 平台 ddw.9cio.com） | 解答使用问题，处理投诉，收集改进建议 |
| 附件识别 | 支持图片引导描述、PDF 文本提取（pymupdf）、邮件解析（.eml）、文本文件 |
| 知识库丰富 | 附件上传后自动 LLM 提炼为 FAQ 格式知识点，追加到知识库 |
| 投诉/建议记录 | 售后模式自动检测投诉/建议关键词，写入 feedback/ 日志（产品迭代来源） |
| 跨页保持 | sessionStorage 保存会话历史和输入框草稿，跳页不丢失 |

### 投诉/建议工作流

1. 用户在 DDW 平台页面（postsales 模式）发送投诉/建议
2. 果果先共情安抚/积极回应
3. 系统自动将投诉/建议写入 `feedback/YYYY-MM-DD.md`
4. 产品团队每日查看反馈日志，纳入迭代评估

### 知识库维护

- **手动更新**：编辑 `knowledge/company.md`，重启 ddw-core
- **自动提炼**：每日 7 点 cron job 扫描 32G 知识库变更 → LLM 提炼 → 追加到 `knowledge/YYYY-MM-DD.md`
- **附件丰富**：客户上传的文档经 LLM 分析后自动提炼为 FAQ 条目
- **红线**：个人信息、公司地址、API 密钥、公司规模、注册资金、成功案例数字 不得作为知识库内容

### API 端点

| 方法 | 路径 | 说明 |
|:--|:--|:--|
| POST | `/api/v1/plugins/ddw_online_cs/chat` | 客服对话（body: message + mode + session_id） |
| POST | `/api/v1/plugins/ddw_online_cs/upload` | 附件上传（form: file + session_id） |
| GET | `/api/v1/plugins/ddw_online_cs/health` | 健康检查 |
| GET | `/api/v1/plugins/ddw_online_cs/knowledge` | 知识库检索调试 |

### 已作废插件

- `customer-service/` → 已标记 DEPRECATED，由 ddw_online_cs 取代
- `ddw-smart-cs/` → 已标记 DEPRECATED，由 ddw_online_cs 取代

### 文件目录

```
plugins/ddw_online_cs/
├── __init__.py        # Plugin 类（平台加载入口）
├── plugin.py          # PluginBase 子类（loader 要求）
├── router.py          # FastAPI 路由（chat/upload/health/knowledge）
├── kb.py              # 轻量 RAG 知识库（纯 stdlib）
├── manifest.yaml      # 插件清单
├── knowledge/         # 知识库文件
│   ├── company.md     # 核心知识（公司/平台/服务/FAQ）
│   └── YYYY-MM-DD.md  # 自动提炼的日期知识条目
├── feedback/          # 投诉/建议日志（售后模式自动写入）
└── uploads/           # 客户上传的原始文件（回传 32G）
```
