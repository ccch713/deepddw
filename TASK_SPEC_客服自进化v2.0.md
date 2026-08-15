# TASK_SPEC：DDW AI 客服自进化 v2.0 升级

> 日期：2026-08-11
> 优先级：P0（嘉必优 Demo 前必须完成）
> 执行者：MiMo Code
> 32G 指挥，16G 辅助知识库搜索

---

## 一、升级目标

在 v1.1 已部署的自进化系统（log_store/insights/curator/asset_builder）基础上，完成 4 项核心升级：

1. **前端反馈闭环**：👍/👎 按钮 + 纠错输入
2. **pgvector 向量库**：替换 md5 哈希桶，实现真正语义检索
3. **行业感知**：URL 参数自动切换行业知识库
4. **钉钉审核推送**：按行业推送到不同审核人

---

## 二、现有代码结构

```
plugins/ddw_online_cs/
├── router.py          # 全部 API（chat/stream/upload/health/knowledge）
├── kb.py              # 纯 stdlib RAG（md5 哈希桶 + 关键词混合检索）
├── plugin.py          # 平台加载入口（Plugin 类）
├── log_store.py       # 对话全量落盘 JSONL（v1.1 已部署）
├── insights.py        # 每日 LLM 评估（v1.1 已部署）
├── curator.py         # 话术库管理 + 混合审核（v1.1 已部署）
├── asset_builder.py   # 资产包构建（v1.1 已部署）
├── knowledge/
│   └── company.md     # 主知识库（2.9KB，内容极少）
├── scripts/           # 话术库（空目录，6 分类 JSON 均未创建）
├── feedback/          # 投诉/建议日志
├── logs/              # 对话日志 JSONL
├── evolution_pool/    # 进化池
├── daily_insights/    # 每日洞察报告
├── pending_review/    # 待审池
├── tests/             # 测试
└── manifest.yaml      # 插件清单
```

前端文件：
```
frontend/company/assets/js/site-common.js   # 全站浮动客服 JS（fcsRender）
frontend/company/assets/css/base.css        # 浮动客服样式
```

---

## 三、4 项升级详细设计

### 升级 1：前端反馈闭环

#### 前端改动（site-common.js）

在每条 AI 回复气泡右下角增加反馈控件：

```
┌─────────────────────────────────┐
│ AI 回复内容...                    │
│                          👍 👎  │
└─────────────────────────────────┘
```

- 点击 👍 → 立即变色确认（✅），调 `POST /api/v1/plugins/ddw_online_cs/feedback` `{session_id, message_id, type: "positive"}`
- 点击 👎 → 弹出输入框「哪里不好？（可选）」→ 调 `POST /api/v1/plugins/ddw_online_cs/feedback` `{session_id, message_id, type: "negative", correction: "..."}`
- 每条消息只能反馈一次，反馈后按钮灰显
- sessionStorage 记录已反馈的 message_id，跨页面保持

#### 后端新增（router.py）

```python
@router.post("/feedback")
async def receive_feedback(
    session_id: str,
    message_id: str,          # 对应 log_store 的 ts 或消息索引
    type: str,                # "positive" | "negative"
    correction: str = "",     # 纠错内容（仅 negative 时有值）
    mode: str = "presales",
):
    """接收用户反馈，写入 feedback/feedback.jsonl + 更新 log_store 对应记录"""
    # 1. 追加写 feedback/feedback.jsonl
    # 2. 如果是 negative 且有 correction，生成改进候选进 evolution_pool
    # 3. return {"ok": true}
```

#### 反馈数据格式（feedback/feedback.jsonl）

```json
{"ts": "2026-08-11T10:30:00+08:00", "session_id": "cs_xxx", "message_id": "msg_003", "type": "negative", "correction": "价格说错了，应该是按年付费", "mode": "presales", "user_msg": "你们多少钱", "ai_reply": "..."}
```

---

### 升级 2：pgvector 向量库

#### ECS 部署

```bash
# 1. 安装 PostgreSQL + pgvector（Docker 方式，复用 ECS 现有 Docker）
docker run -d \
  --name ddw-pgvector \
  --restart unless-stopped \
  -e POSTGRES_PASSWORD=<随机生成> \
  -e POSTGRES_DB=ddw_kb \
  -v /opt/ddw/pgvector-data:/var/lib/postgresql/data \
  -p 127.0.0.1:5433:5432 \
  pgvector/pgvector:pg16

# 2. 启用 pgvector 扩展
docker exec ddw-pgvector psql -U postgres -d ddw_kb -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 3. 创建知识库表
docker exec ddw-pgvector psql -U postgres -d ddw_kb -c "
CREATE TABLE IF NOT EXISTS kb_chunks (
    id SERIAL PRIMARY KEY,
    industry VARCHAR(50) NOT NULL DEFAULT 'general',
    content TEXT NOT NULL,
    source VARCHAR(255),
    embedding vector(1024),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_industry ON kb_chunks(industry);
CREATE INDEX IF NOT EXISTS idx_kb_chunks_embedding ON kb_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);
"
```

#### kb.py 重写

将 `kb.py` 的 md5 哈希向量替换为真正的 embedding 检索：

```python
# 方案：调用 MiniMax embedding API（或本地 bge-m3）
# 向量维度：1024（bge-m3 默认维度）
# 检索方式：余弦相似度 top_k

class KnowledgeBase:
    def __init__(self, pg_dsn: str, industry: str = "general"):
        self.pg_dsn = pg_dsn
        self.industry = industry
    
    async def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """pgvector 余弦相似度检索"""
        embedding = await self._embed(query)
        # SELECT content, source, 1 - (embedding <=> $1) as similarity
        # FROM kb_chunks WHERE industry = $2
        # ORDER BY embedding <=> $1 LIMIT $3
    
    async def ingest(self, content: str, source: str, industry: str = None):
        """知识入库"""
        chunks = self._chunk(content)
        for chunk in chunks:
            embedding = await self._embed(chunk)
            # INSERT INTO kb_chunks (industry, content, source, embedding) VALUES (...)
    
    async def _embed(self, text: str) -> List[float]:
        """调用 MiniMax embedding API 或本地 bge-m3"""
        # MiniMax: POST https://api.minimaxi.com/v1/embeddings
        # 本地: sentence-transformers bge-m3
```

#### Embedding 选型

| 方案 | 优点 | 缺点 | 建议 |
|:-----|:-----|:-----|:-----|
| MiniMax embedding API | 零部署，套餐内 | API 延迟，外部依赖 | **Phase 1 用这个** |
| 本地 bge-m3 (MLX) | 零成本，无延迟 | 需要 32G 设备运行 | Phase 2 迁移 |
| OpenAI text-embedding-3 | 效果最好 | 要钱，要翻墙 | ❌ |

---

### 升级 3：行业感知

#### 前端（site-common.js）

```javascript
// 从当前 URL 推断行业
function detectIndustry() {
    const path = window.location.pathname;
    if (path.includes('dental') || path.includes('clinic')) return 'dental';
    if (path.includes('food') || path.includes('quality')) return 'food';
    if (path.includes('esg')) return 'esg';
    if (path.includes('manufacturing')) return 'manufacturing';
    // URL 参数优先
    const params = new URLSearchParams(window.location.search);
    return params.get('industry') || 'general';
}
```

API 请求 JSON 新增 `industry` 字段。

#### 后端（router.py）

```python
# 知识库检索时按 industry 过滤
kb = KnowledgeBase(pg_dsn, industry=industry)
results = await kb.search(query, top_k=5)

# system prompt 追加行业上下文
if industry != "general":
    system_prompt += f"\n\n【当前行业上下文：{_INDUSTRY_NAMES[industry]}】\n"
    system_prompt += _INDUSTRY_PROMPTS.get(industry, "")
```

#### 行业目录结构（knowledge/ 下）

```
knowledge/
├── general/          # 通用知识（公司/平台/服务）
│   └── company.md
├── dental/           # 口腔医疗
│   ├── diseases.md   # 常见口腔疾病
│   ├── treatments.md # 诊疗项目
│   └── faq.md        # 患者常见问题
├── food/             # 食品行业
│   ├── regulations.md # 法律法规
│   ├── standards.md   # GB标准
│   └── faq.md         # 质量管理FAQ
├── esg/              # ESG合规
│   ├── frameworks.md  # ESG框架
│   ├── standards.md   # 合规标准
│   └── faq.md         # ESG常见问题
└── manufacturing/    # 制造业（后续扩展）
```

---

### 升级 4：钉钉审核推送

#### 审核人路由配置（新增 config/deployment.yaml 段）

```yaml
cs_evolution:
  review_channels:
    dental:
      platform: dingtalk
      webhook: "<夫人的钉钉机器人 webhook>"
      mention: "<夫人的钉钉 userId>"
    food:
      platform: weixin
      webhook: "<嘉必优对接人的企微 webhook>"
    esg:
      platform: weixin
      webhook: "<嘉必优对接人的企微 webhook>"
    manufacturing:
      platform: dingtalk
      webhook: "<CNC朋友的钉钉 webhook>"
    general:
      platform: dingtalk
      webhook: "<默认审核钉钉 webhook>"
```

#### curator.py 改动

```python
def _push_review_notification(self, items: List[Dict], industry: str):
    """推送审核通知到对应审核人"""
    channel = self.review_channels.get(industry, self.review_channels["general"])
    
    if channel["platform"] == "dingtalk":
        # 钉钉机器人 webhook 推送
        # POST webhook, 消息体含：待审条目数 + 每条摘要 + "回复 通过 <id> / 否决 <id>"
        pass
    elif channel["platform"] == "weixin":
        # 企微机器人 webhook 推送
        pass
```

---

## 四、知识库初始内容（32G 负责生成，已同步进行）

| 行业 | 文件 | 内容来源 | 状态 |
|:-----|:-----|:---------|:-----|
| general | company.md | Obsidian DDW 文档提取（去除架构/价格/底层逻辑） | 32G 正在提取 |
| dental | diseases.md + treatments.md + faq.md | 口腔医学专业知识 | 32G 正在生成 |
| food | regulations.md + standards.md + faq.md | 食品添加剂 GB 标准 + 法规 | 32G 正在生成 |
| esg | frameworks.md + standards.md + faq.md | ESG 合规框架 | 32G 正在生成 |

**知识库安全红线**：
- ❌ 不含 DDW 架构设计、底层逻辑、代码实现细节
- ❌ 不含价格信息（定价、成本、套餐详情）
- ❌ 不含客户隐私数据
- ❌ 不含公司规模、注册资金、合同金额
- ✅ 只含产品功能说明、使用帮助、行业通用知识

---

## 五、验收标准

| # | 验收项 | 方法 |
|:--|:-----|:-----|
| 1 | 👍/👎 按钮可见 | 打开 www.9cio.com，AI 回复右下角有反馈按钮 |
| 2 | 反馈写入 ECS | 点击 👎 + 输入纠错 → ECS feedback/feedback.jsonl 有记录 |
| 3 | pgvector 建库成功 | `docker exec ddw-pgvector psql -U postgres -d ddw_kb -c "SELECT COUNT(*) FROM kb_chunks;"` > 0 |
| 4 | 语义检索生效 | 搜索"牙齿矫正"能命中"正畸治疗"相关知识 |
| 5 | 行业切换 | 访问 `www.9cio.com/industry-dental.html` 的客服，回答含口腔专业内容 |
| 6 | 钉钉推送 | 触发低置信进化 → 钉钉收到审核通知 |
| 7 | 回归测试 | 现有 chat/stream/upload/health 全部正常 |

---

## 六、开发顺序

1. **pgvector Docker 部署**（ECS，30 分钟）
2. **kb.py 重写**（pgvector + MiniMax embedding，2 小时）
3. **knowledge/ 目录迁移**（md 文件 → pgvector 入库，1 小时）
4. **前端反馈按钮**（site-common.js，1.5 小时）
5. **后端 feedback 端点**（router.py，30 分钟）
6. **行业感知**（前端 detectIndustry + 后端 industry 过滤，1 小时）
7. **钉钉审核推送**（curator.py + webhook 配置，1 小时）
8. **集成测试 + 部署**（1 小时）

**预计总工时：8 小时**

---

## 七、部署清单

### ECS 新增 Docker 容器

```yaml
# docker-compose 加入
services:
  ddw-pgvector:
    image: pgvector/pgvector:pg16
    container_name: ddw-pgvector
    restart: unless-stopped
    environment:
      POSTGRES_DB: ddw_kb
      POSTGRES_PASSWORD: ${PGVECTOR_PASSWORD}
    volumes:
      - /opt/ddw/pgvector-data:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5433:5432"
    networks:
      - ddw-net
```

### ddw_env 新增环境变量

```
PGVECTOR_DSN=postgresql://postgres:${PGVECTOR_PASSWORD}@127.0.0.1:5433/ddw_kb
MINIMAX_EMBEDDING_URL=https://api.minimaxi.com/v1/embeddings
```

---

## 八、风险与对策

| 风险 | 对策 |
|:-----|:-----|
| ECS 内存不足（2GB 已紧张） | pgvector Docker 限制内存 256MB（小知识库够用） |
| MiniMax embedding API 不可用 | 降级到 md5 哈希桶（保留旧 kb.py 作为 fallback） |
| 行业知识内容有误 | 钉钉审核机制兜底，人工确认后才入库 |
| 前端反馈被滥用 | 单 session 每条消息只能反馈一次 |
