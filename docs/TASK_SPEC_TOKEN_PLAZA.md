# TASK_SPEC: Token 广场（原 LLM 网关）

> 优先级：P0  
> 预计工时：3-4 天  
> 插件名：ddw_token_plaza  
> 状态：待确认

---

## 1. 概述

Token 广场是 DDW 的 LLM 管理和消耗可视化中心。包含 3 个子模块：
- **LLM 配置**：管理云端/本地 LLM provider，按 10 类能力分类
- **消耗统计**：四级 ACL（员工/部门/公司/董事长）的 token 消耗可视化
- **API Key 管理**：仅公司级可配置

**核心规则：**
- SaaS 默认提供 MiniMax M3 云端 LLM，**对所有用户不可见**
- LLM 网关用量对 SaaS 用户**仅显示"平台公用 LLM"汇总**
- 租户公司级管理员可添加自定义 provider，用量展示**租户定义名**
- 未定义名称的 provider 回退到配置时的 provider 名

## 2. LLM 能力分类（10 类）

| # | 能力标识 | 用途 | 参考 OpenMAIC |
|---|---------|------|--------------|
| 1 | chat | 日常文本对话 | providers |
| 2 | vision | 识图（多模态图像理解） | —（扩） |
| 3 | asr | 语音识别 | asr |
| 4 | pdf | PDF 识别/解析 | pdf |
| 5 | ocr | OCR 识别（图片文字提取） | —（扩） |
| 6 | image_gen | 图片生成 | image |
| 7 | web_search | 网页搜索 | web-search |
| 8 | tts | 语音输出（文字转语音） | tts |
| 9 | image_edit | 图片输出（修图/换风格） | —（扩） |
| 10 | video_gen | 视频生成 | video |

## 3. 数据模型

### 3.1 LLM Provider（LLMProvider）

```python
class LLMProvider(Base):
    __tablename__ = "llm_providers"
    
    id: int = Column(Integer, primary_key=True)
    tenant_id: int = Column(Integer, nullable=True)           # null = 平台级（隐藏）
    name: str = Column(String(100), nullable=False)           # 用户定义名
    provider_type: str = Column(String(50), nullable=False)   # minimax/deepseek/openai/local/...
    base_url: str = Column(String(500), nullable=False)
    api_key_enc: str = Column(Text, nullable=True)            # 加密存储
    capabilities: list = Column(JSON, default=["chat"])       # 支持的能力列表（10类中的子集）
    hosting_type: str = Column(String(20), default="tenant_cloud")  # platform / tenant_cloud / tenant_self_hosted
    display_name: str = Column(String(100), nullable=True)    # 用户自定义显示名（fallback 到 name）
    is_default: bool = Column(Boolean, default=False)         # 是否为该租户默认 provider
    status: str = Column(String(20), default="active")
    created_at: datetime = Column(DateTime, default=utcnow)
```

### 3.2 LLM 用量记录（扩展 llm_usage_records）

```sql
-- 在现有 llm_usage_records 表上新增字段
ALTER TABLE llm_usage_records ADD COLUMN hosting_type TEXT DEFAULT 'platform';
-- hosting_type: 'platform' / 'tenant_cloud' / 'tenant_self_hosted'
ALTER TABLE llm_usage_records ADD COLUMN tenant_id INTEGER;
ALTER TABLE llm_usage_records ADD COLUMN user_id INTEGER;
```

### 3.3 LLM 自选开关（TenantLLMConfig）

```python
class TenantLLMConfig(Base):
    __tablename__ = "tenant_llm_configs"
    
    id: int = Column(Integer, primary_key=True)
    tenant_id: int = Column(Integer, ForeignKey("tenants.id"), unique=True)
    allow_employee_choice: bool = Column(Boolean, default=False)  # 公司级开关
    min_providers_for_choice: int = Column(Integer, default=2)    # 自选需≥N个provider
    updated_at: datetime = Column(DateTime, default=utcnow)
```

## 4. 消耗统计 — 四级 ACL

### 4.1 员工级

- 仅看到**自己的** token 消耗
- 饼图：按能力分类占比（chat/vision/ocr/...）
- 饼图：按 LLM provider 占比
- 明细表：最近 20 条调用记录

### 4.2 部门管理员级

- 本部门所有员工 + 数字员工的 token 消耗分布
- 统计维度：skill / 识图 / 对话 / 员工A / 员工B / ...
- 部门 Token 龙虎榜：所有部门月度总消耗**降序**（但仅显示部门名+总量，不显示其他部门详细信息）

### 4.3 公司管理员级

- 全公司所有部门的消耗总览
- 所有维度均可查看
- 可看到每个 provider 的详细消耗（自定义名称或配置名）
- 隐藏的"平台公用 LLM"汇总

### 4.4 董事长级

- owner 可设置某员工为"chairman"角色
- chairman 默认可见**全部报表** + **所有部门员工的 token 消耗数据**
- 与公司管理员看到的内容相同

## 5. 消耗统计 — 云端 vs 自建 GPU 双轨展示

```
Token 广场 > 消耗统计

┌─────────────────────────────────────────────────┐
│  📊 Token 消耗总览（近 7 天）                    │
│                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│  │ 总调用   │ │ 输入Token│ │ 输出Token│        │
│  │ 1,234    │ │ 567.8w   │ │ 234.5w   │        │
│  └──────────┘ └──────────┘ └──────────┘        │
│                                                  │
│  ☁️ 云端 LLM 消耗                                │
│  ┌─────────────────────────────────────────┐    │
│  │ Provider    │ 模型       │ Token │ 预估支出│    │
│  │ 平台公用LLM │ —          │ 100w  │ —      │    │
│  │ DeepSeek    │ v4-pro     │ 50w   │ ¥12.50 │    │
│  │ MiniMax     │ M3         │ 30w   │ ¥8.40  │    │
│  └─────────────────────────────────────────┘    │
│                                                  │
│  🖥️ 自建 GPU 算力消耗                            │
│  ┌─────────────────────────────────────────┐    │
│  │ Provider    │ 模型       │ Token │ 预估节约│    │
│  │ 嘉必优GPU1  │ Qwen3-27B  │ 200w  │ ¥56.00 │    │
│  │ 嘉必优GPU2  │ LLaMA-70B  │ 80w   │ ¥32.00 │    │
│  └─────────────────────────────────────────┘    │
│  节约金额 = 原厂云端单价 × 自建算力 token 数      │
└─────────────────────────────────────────────────┘
```

## 6. API Key 管理（仅公司级）

```yaml
GET    /api/v1/token/apikeys                      # 列表
POST   /api/v1/token/apikeys                      # 创建
DELETE /api/v1/token/apikeys/{id}                  # 删除
```

- API Key 从原来的"成员"频道移到 Token 广场下
- 仅 owner 和 admin 角色可操作

## 7. API 端点

```yaml
# LLM Provider
GET    /api/v1/token/providers                    # 列表（SaaS 用户仅显示自定义的）
POST   /api/v1/token/providers                    # 添加 provider
PUT    /api/v1/token/providers/{id}               # 修改
DELETE /api/v1/token/providers/{id}               # 删除
GET    /api/v1/token/providers/capabilities       # 返回 10 类能力列表

# LLM 自选开关
GET    /api/v1/token/config                       # 获取租户 LLM 配置
PUT    /api/v1/token/config                       # 修改（仅 company admin）

# 消耗统计
GET    /api/v1/token/usage?days=7                 # 当前用户/部门/公司级消耗（按 ACL 自动裁剪）
GET    /api/v1/token/usage/dept-leaderboard       # 部门 Token 龙虎榜
GET    /api/v1/token/usage/savings                # 自建 GPU 节约金额统计
```

## 8. 前端页面

### 8.1 LLM 配置（saas-admin.html#/token-llm）

- 列表展示租户自定义 provider（不显示平台级）
- 添加 provider 表单：名称、类型、base_url、API Key、能力多选（10 类）
- 每个 provider 可编辑/删除
- 底部提示："如需使用更多 LLM，请联系平台管理员"

### 8.2 消耗统计（saas-admin.html#/token-usage）

- 按四级 ACL 展示不同内容（见上）
- 云端 vs 自建 GPU 双轨表格
- 预估支出 = 单价 × token 数
- 预估节约 = 原厂云端单价 × 自建算力 token 数

### 8.3 API Key（saas-admin.html#/token-apikeys）

- 复用原有 saas-admin 的 API Key 页面逻辑，迁移到此

## 9. 验收标准

| # | 验证项 | 预期结果 |
|---|--------|----------|
| 1 | 添加自定义 provider | 出现在列表中 |
| 2 | "平台公用 LLM" | SaaS 用户看不到 MiniMax-M3 字样 |
| 3 | 消耗统计（员工级） | 仅看到自己的调用 |
| 4 | 消耗统计（部门级） | 看到本部门 + 龙虎榜（仅部门名+总量） |
| 5 | 消耗统计（公司级） | 看到全部 |
| 6 | 自选开关 | 关闭时员工不可选 LLM；开启时且≥2个provider才生效 |
| 7 | 双轨展示 | 云端/自建分别展示，节约金额正确计算 |

## 10. 依赖

- 现有 core/llm_gateway/usage.py 的 llm_usage_records 表需扩展字段
- 现有 core/api/admin.py 的 /llm/usage 需重构为按 ACL 裁剪
