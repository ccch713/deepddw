# DDW 设计院智能解决方案 · 产品需求文档（PRD）

> 版本：v1.0.0
> 日期：2026-08-02
> 项目可见性：私有商业（仅 Gitea + 公司官网宣传）
> 目标客户：中小型设计院（从大型设计院驻地方办事处切入）

---

## 一、产品概述

### 1.1 产品定位
DDW 设计院智能解决方案是一套基于 DDW AI Hub 平台的插件群，面向建筑工程设计院提供"资质管理 + 投标书撰写 + 造价知识库"三位一体的 AI 智能化工具。

### 1.2 核心差异化
- **自托管**：数据不出院内网络，工程图纸/造价数据/投标文件全程保密
- **行业垂直**：基于设计院真实业务流程设计，非通用 AI 工具
- **知识积累**：历史项目数据沉淀为可复用的知识资产
- **插件组合**：按需装配，今天用资质管理，明天加投标书生成

### 1.3 目标客户画像
- 中小型建筑设计院/市政设计院（乙级、丙级）
- 大型设计院的地方办事处/分支机构
- 造价咨询公司
- 投标频率：每月 3-10 次
- IT 预算：有限，偏好一次性买断或低成本订阅

### 1.4 插件群全景

| 插件名 | 功能定位 | 优先级 |
|--------|---------|--------|
| ddw-personnel-qual | 设计人员资质管理 | P0 |
| ddw-bid-writer | 投标标书撰写（含多风格差异化） | P0 |
| ddw-cost-knowledge | 历史造价知识库 | P1 |

---

## 二、插件 1：ddw-personnel-qual（设计人员资质管理）

### 2.1 业务场景
设计院在投标时需要快速匹配"项目所需资质 → 可用持证人员"。目前靠 Excel 和人工记忆，效率低、易出错。住建部"人证合一"监管趋严，挂证风险管控需求迫切。

### 2.2 功能清单

#### 2.2.1 证书台账管理
- **支持的证书类型**（全覆盖）：
  - 注册建筑师（一级/二级）
  - 注册结构工程师（一级/二级）
  - 注册设备工程师（暖通/给排水/电气）
  - 注册监理工程师
  - 注册造价工程师
  - 注册咨询工程师
  - 注册建造师（一级/二级，建筑工程/市政公用/机电等）
  - 安全工程师
  - 其他行业证书（可自定义扩展）
- **每条证书记录包含**：
  - 姓名、身份证号、联系电话
  - 证书类型、证书编号、注册号
  - 发证日期、有效期至、注册单位
  - 专业方向（建筑/结构/暖通/给排水/电气等）
  - 当前状态：在用/闲置/到期预警/已过期
  - 关联项目（参与过的投标/在建项目）
- **批量导入**：支持 Excel 模板导入（一次导入全院证书数据）

#### 2.2.2 智能到期预警
- **预警规则**：
  - 证书到期前 90/60/30/7 天分级提醒
  - 继教育学时不足预警
  - 注册单位与实际工作单位不一致预警（挂证风险）
- **提醒方式**：
  - 系统内通知
  - 飞书/企微/钉钉推送（通过 DDW 适配器）
  - 邮件提醒（通过 ddw-email-assistant）
- **预警看板**：一页展示全院证书健康状态（绿/黄/红三色）

#### 2.2.3 投标人员智能匹配
- **输入**：招标文件中的资质要求（如"项目经理需一级建造师，近5年2个以上10万㎡住宅项目业绩"）
- **处理**：AI 解析资质要求 → 匹配院内可用人员 → 生成推荐名单
- **输出**：
  - 满足全部要求的人员列表（按匹配度排序）
  - 部分满足的人员列表（标注缺失项）
  - 可用人员的证书详情 + 历史项目业绩
- **约束检查**：
  - 人员是否已被其他在建项目占用
  - 人员证书是否在有效期内
  - 人员是否有在建项目冲突（"人证合一"检查）

#### 2.2.4 人员全景视图
- **个人档案**：每个持证人员的完整信息页
  - 证书列表、参与项目、业绩记录、荣誉奖项
  - 时间线视图：何时入职、何时取得证书、何时参与项目
- **组织架构视图**：按部门/专业查看人员分布
  - 各专业持证人数统计
  - 证书类型分布图表
  - 人员利用率分析

### 2.3 数据模型

```python
# 核心实体
class Personnel(Base):
    id: int                    # 主键
    name: str                  # 姓名
    id_card: str               # 身份证号（加密存储）
    phone: str                 # 联系电话
    department: str            # 所属部门
    position: str              # 职位
    join_date: date            # 入职日期
    status: str                # 在职/离职/休假

class Certificate(Base):
    id: int                    # 主键
    personnel_id: int          # 关联人员
    cert_type: str             # 证书类型（枚举）
    cert_name: str             # 证书名称
    cert_number: str           # 证书编号
    register_number: str       # 注册号
    issue_date: date           # 发证日期
    expiry_date: date          # 有效期至
    specialty: str             # 专业方向
    issuing_authority: str     # 发证机关
    register_unit: str         # 注册单位
    status: str                # 在用/闲置/到期预警/已过期
    continuing_education: int  # 继教育学时

class ProjectRecord(Base):
    id: int                    # 主键
    personnel_id: int          # 关联人员
    project_name: str          # 项目名称
    project_type: str          # 项目类型
    role: str                  # 担任角色（项目经理/技术负责人/专业负责人）
    start_date: date           # 开始日期
    end_date: date             # 结束日期
    area: float                # 建筑面积（㎡）
    amount: float              # 项目金额（万元）
    result: str                # 项目结果（中标/在建/完工）

class AlertRule(Base):
    id: int                    # 主键
    cert_type: str             # 适用证书类型
    alert_days: int            # 提前天数
    alert_type: str            # 到期预警/继教育/挂证风险
    notify_channels: str       # 通知渠道（JSON数组）
    enabled: bool              # 是否启用
```

### 2.4 API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/personnel | 创建人员 |
| GET | /api/personnel | 查询人员列表（分页+筛选） |
| GET | /api/personnel/{id} | 人员详情 |
| PUT | /api/personnel/{id} | 更新人员 |
| POST | /api/personnel/import | 批量导入（Excel） |
| POST | /api/certificates | 添加证书 |
| GET | /api/certificates | 查询证书列表 |
| PUT | /api/certificates/{id} | 更新证书 |
| GET | /api/certificates/expiring | 即将到期证书列表 |
| POST | /api/match | 投标人员智能匹配 |
| GET | /api/dashboard | 资质管理看板数据 |
| GET | /api/statistics | 人员/证书统计 |
| POST | /api/alerts/check | 触发预警检查 |
| GET | /api/alerts | 预警记录列表 |

### 2.5 资源消耗声明

| 维度 | 评估 |
|------|------|
| 基础内存 | ~30 MB |
| 峰值内存 | ~80 MB（批量导入时） |
| 数据库存储 | ~5 MB/年（100人规模） |
| LLM Token | 仅"智能匹配"功能调用，约 2000 tokens/次 |
| 外部依赖 | 无（纯本地运行） |
| 评级 | **轻量级** |

---

## 三、插件 2：ddw-bid-writer（投标标书撰写）

### 3.1 业务场景
设计院投标时需要撰写技术标和商务标，通常耗时 3-7 天。标书格式要求严格，废标风险高。同一项目多家投标时需要差异化内容。

### 3.2 功能模块

#### 3.2.1 招标文件智能解析
- **输入**：上传招标文件（PDF/Word/扫描件）
- **处理**：
  - OCR 文字识别（扫描件/图片）
  - NLP 语义分析：提取评分标准、资质要求、技术参数、工期要求、废标条款
  - 结构化输出：生成招标要点清单
- **输出**：
  - 评分细则表（每条评分项 + 分值 + 响应要求）
  - 资质要求清单（对应 ddw-personnel-qual 的匹配输入）
  - 废标风险点列表
  - 技术参数要求表

#### 3.2.2 标书智能生成
- **标书结构**（设计院投标标准模块）：

| 模块 | 内容 | AI 生成能力 |
|------|------|-----------|
| 商务标 | 企业资质、业绩、财务、信誉 | 从企业知识库自动填充 |
| 技术标-项目概述 | 项目背景、理解、设计范围 | AI 基于招标文件生成 |
| 技术标-设计理念 | 设计哲学、创新思路 | AI 生成 + 人工调整 |
| 技术标-技术方案 | 各专业技术路线、难点分析 | AI 基于项目类型生成 |
| 技术标-实施计划 | 进度计划、人员配置、设备 | AI 生成甘特图 + 人员表 |
| 技术标-质量控制 | 质量管理体系、保证措施 | 模板化生成 |
| 技术标-风险管理 | 风险识别、应对措施 | AI 基于项目特征生成 |
| 技术标-成本预算 | 报价说明、成本分析 | 结合 ddw-cost-knowledge |

- **企业知识库**：
  - 上传历史标书（Word/PDF）→ AI 提取可复用内容
  - 上传企业资质证书、业绩证明 → 自动关联到标书
  - 上传技术方案模板 → AI 参考旧稿写新稿
  - 本地 LLM 自动提炼学习，保存到知识库

- **AI 生成流程**：
  ```
  招标文件解析 → 评分点映射 → 大纲生成 → 逐章生成 → 合规检查 → 排版输出
  ```

#### 3.2.3 多风格差异化生成（投标修饰功能）
- **功能定位**：当同一项目需要投递多份标书时，系统自动生成内容差异化版本
- **功能入口**：标书生成界面的"高级选项"中，以多选框形式呈现
- **可选修饰维度**（用户自行勾选）：
  - ☐ 措辞风格差异（正式/学术/务实/创新）
  - ☐ 章节结构调整（章节顺序/详略分布）
  - ☐ 图表排版差异（图表类型/布局/配色）
  - ☐ 表述方式差异（数据呈现/案例引用/论证逻辑）
  - ☐ 专业术语替换（同义术语/行业变体）
- **技术实现**：
  - 基于 LLM 的语义改写（非简单换词）
  - 保持内容准确性和专业性
  - 生成后自动查重，确保差异化
  - 支持预览对比（原文 vs 改写版）
- **UI 设计**：
  - 不在界面中解释功能用途
  - 仅显示"投标书修饰"标题 + 维度多选框 + "生成"按钮
  - 功能说明通过线下沟通传递

#### 3.2.4 标书合规检查
- **格式检查**：字体、页边距、页眉页脚、装订要求
- **内容检查**：
  - 评分点逐条响应检查
  - 资质要求匹配检查（联动 ddw-personnel-qual）
  - 废标条款风险检查
  - 数据一致性检查（金额/工期/人员等）
- **查重检查**：内容重复率检测（与历史标书对比）

#### 3.2.5 标书排版输出
- **输出格式**：Word（.docx）
- **排版规则**：
  - 按招标文件格式要求自动排版
  - 支持自定义模板
  - 自动插入表格、流程图、甘特图
  - 页码自动生成
- **批量输出**：支持一次生成多份差异化标书

### 3.3 数据模型

```python
class BidProject(Base):
    id: int                    # 主键
    name: str                  # 项目名称
    client: str                # 招标方
    bid_deadline: datetime     # 投标截止时间
    estimated_amount: float    # 预估金额
    status: str                # 解析中/撰写中/审核中/已完成
    bid_type: str              # 设计标/施工标/监理标/咨询标
    created_at: datetime
    updated_at: datetime

class BidDocument(Base):
    id: int                    # 主键
    project_id: int            # 关联项目
    version: int               # 版本号
    style_variant: str         # 风格变体标识（standard/style_a/style_b...）
    content: text              # 标书内容（结构化JSON）
    word_count: int            # 字数
    compliance_score: float    # 合规评分
    duplicate_rate: float      # 重复率
    status: str                # 草稿/已生成/已审核/已导出
    created_at: datetime

class BidTemplate(Base):
    id: int                    # 主键
    name: str                  # 模板名称
    category: str              # 设计标/施工标/监理标
    module: str                # 适用模块（技术标/商务标）
    content: text              # 模板内容
    is_default: bool           # 是否默认模板

class BidKnowledge(Base):
    id: int                    # 主键
    source_type: str           # 历史标书/企业资质/业绩证明/技术方案
    source_file: str           # 原始文件路径
    extracted_content: text    # AI 提取的可复用内容
    tags: str                  # 标签（JSON数组）
    created_at: datetime

class BidCheckResult(Base):
    id: int                    # 主键
    document_id: int           # 关联标书
    check_type: str            # format/content/compliance/duplicate
    item: str                  # 检查项
    status: str                # pass/warning/fail
    detail: text               # 详细说明
    suggestion: text           # 修改建议
```

### 3.4 API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/projects | 创建投标项目 |
| GET | /api/projects | 查询项目列表 |
| GET | /api/projects/{id} | 项目详情 |
| POST | /api/projects/{id}/parse | 解析招标文件 |
| GET | /api/projects/{id}/parse-result | 解析结果 |
| POST | /api/projects/{id}/generate | 生成标书 |
| POST | /api/projects/{id}/generate-variant | 生成差异化版本 |
| GET | /api/projects/{id}/documents | 标书版本列表 |
| GET | /api/documents/{id} | 标书内容 |
| POST | /api/documents/{id}/check | 合规检查 |
| GET | /api/documents/{id}/check-results | 检查结果 |
| POST | /api/documents/{id}/export | 导出 Word |
| POST | /api/knowledge/upload | 上传知识库素材 |
| GET | /api/knowledge | 知识库列表 |
| GET | /api/templates | 标书模板列表 |
| POST | /api/templates | 创建模板 |

### 3.5 资源消耗声明

| 维度 | 评估 |
|------|------|
| 基础内存 | ~80 MB |
| 峰值内存 | ~300 MB（大标书生成时） |
| 数据库存储 | ~50 MB/年（含标书内容） |
| LLM Token | 核心消耗：解析约 5000 tokens + 生成约 20000-50000 tokens/份 |
| 外部依赖 | OCR 引擎（可选，扫描件处理） |
| 评级 | **中等级** |

---

## 四、插件 3：ddw-cost-knowledge（历史造价知识库）

### 4.1 业务场景
设计院积累了大量历史项目的造价数据（Excel 预算表、PDF 结算报告、广联达导出文件等），但这些数据分散在各项目负责人手中，无法被新项目复用。造价估算依赖个人经验，缺乏数据驱动。

### 4.2 功能模块

#### 4.2.1 知识库导入与提炼
- **导入方式**：
  1. 用户在"知识库提炼"对话框中粘贴文件夹路径
  2. DDW + 本地部署 LLM 自动扫描该文件夹
  3. 识别并提取以下格式的造价数据：
     - Excel 预算表/结算表（.xlsx/.xls）
     - PDF 造价报告/结算报告
     - 广联达导出文件（.gbq/.gccp）
     - 造价咨询报告
  4. 自动结构化提取：
     - 项目基本信息（名称、类型、面积、地点、年份）
     - 分部分项工程量清单
     - 材料价格信息
     - 人工费、机械费
     - 综合单价、合价
     - 取费标准、税率
  5. 提炼结果保存到本地知识库
- **导入进度**：
  - 显示扫描进度（已扫描/总文件数）
  - 显示提取结果预览
  - 支持手动修正提取错误

#### 4.2.2 造价知识库查询
- **自然语言查询**：
  - "2024年武汉市10万㎡住宅项目的钢筋工程造价大概是多少？"
  - "类似的商业综合体项目，暖通工程占比通常是多少？"
  - "最近3年混凝土价格趋势如何？"
- **结构化筛选**：
  - 按项目类型、面积范围、地区、年份筛选
  - 按专业（建筑/结构/暖通/给排水/电气）筛选
  - 按造价阶段（估算/概算/预算/结算）筛选
- **查询结果**：
  - 匹配的历史项目列表
  - 造价指标汇总（单方造价、各专业占比）
  - 材料价格参考
  - 趋势分析图表

#### 4.2.3 造价估算辅助
- **输入**：新项目的基本参数（类型、面积、地区、结构形式、装修标准）
- **处理**：
  - 从知识库中匹配相似历史项目
  - 基于历史数据生成造价估算区间
  - 考虑时间调整系数（物价上涨）
  - 考虑地区调整系数
- **输出**：
  - 造价估算报告（分部分项）
  - 与相似项目的对比分析
  - 置信度评估（高/中/低）
  - 建议进一步细化的方向

#### 4.2.4 造价指标看板
- **全院造价数据概览**：
  - 历史项目数量、总造价规模
  - 各类型项目单方造价分布
  - 各专业造价占比趋势
  - 材料价格波动曲线
- **数据更新**：每次导入新项目数据后自动更新

### 4.3 数据模型

```python
class CostProject(Base):
    id: int                    # 主键
    name: str                  # 项目名称
    project_type: str          # 项目类型（住宅/商业/公建/工业/市政）
    location: str              # 项目地点
    area: float                # 建筑面积（㎡）
    structure_type: str        # 结构形式（框架/剪力墙/钢结构）
    decoration_level: str      # 装修标准（毛坯/简装/精装）
    year: int                  # 数据年份
    cost_stage: str            # 造价阶段（估算/概算/预算/结算）
    total_cost: float          # 总造价（万元）
    unit_cost: float           # 单方造价（元/㎡）
    source_file: str           # 来源文件路径
    source_format: str         # 文件格式（xlsx/pdf/gbq）
    created_at: datetime

class CostItem(Base):
    id: int                    # 主键
    project_id: int            # 关联项目
    category: str              # 分部工程（土建/安装/装饰/市政）
    sub_category: str          # 分项工程
    item_name: str             # 清单项目名称
    quantity: float            # 工程量
    unit: str                  # 单位
    unit_price: float          # 综合单价
    amount: float              # 合价
    material_cost: float       # 材料费
    labor_cost: float          # 人工费
    machine_cost: float        # 机械费

class MaterialPrice(Base):
    id: int                    # 主键
    material_name: str         # 材料名称
    specification: str         # 规格型号
    unit: str                  # 单位
    price: float               # 单价
    region: str                # 地区
    year: int                  # 年份
    month: int                 # 月份
    source: str                # 数据来源

class CostIndex(Base):
    id: int                    # 主键
    project_type: str          # 项目类型
    specialty: str             # 专业
    index_name: str            # 指标名称（单方造价/占比/含量）
    value: float               # 指标值
    unit: str                  # 单位
    sample_count: int          # 样本数量
    confidence: str            # 置信度（高/中/低）
    region: str                # 地区
    year_from: int             # 数据起始年份
    year_to: int               # 数据截止年份
```

### 4.4 API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | /api/knowledge/import | 导入文件夹路径，启动提炼 |
| GET | /api/knowledge/import-status | 导入进度查询 |
| GET | /api/knowledge/projects | 造价项目列表 |
| GET | /api/knowledge/projects/{id} | 造价项目详情 |
| POST | /api/knowledge/query | 自然语言查询 |
| POST | /api/knowledge/estimate | 造价估算 |
| GET | /api/knowledge/index | 造价指标列表 |
| GET | /api/knowledge/materials | 材料价格查询 |
| GET | /api/knowledge/dashboard | 造价看板数据 |
| POST | /api/knowledge/validate | 提取结果手动修正 |

### 4.5 资源消耗声明

| 维度 | 评估 |
|------|------|
| 基础内存 | ~50 MB |
| 峰值内存 | ~200 MB（大批量导入时） |
| 数据库存储 | ~100 MB/年（100个项目规模） |
| LLM Token | 导入提炼：约 10000 tokens/文件；查询：约 2000 tokens/次 |
| 外部依赖 | 本地 LLM（必选）、OCR（可选，扫描件PDF） |
| 评级 | **中等级** |

---

## 五、插件间依赖关系

```
ddw-cost-knowledge（造价知识库）
    ↑ 数据支撑
    ├── ddw-bid-writer（标书撰写 → 技术标-成本预算模块）
    └── ddw-cost-estimation（远期 → 造价估算）

ddw-personnel-qual（资质管理）
    ↑ 数据支撑
    └── ddw-bid-writer（标书撰写 → 商务标-人员配置模块 + 投标人员匹配）

ddw-bid-writer（标书撰写）
    ├── 依赖 ddw-personnel-qual（人员匹配）
    └── 依赖 ddw-cost-knowledge（造价数据）
```

**独立性**：三个插件可独立使用，也可组合使用。组合使用时数据互通。

---

## 六、部署架构

```
DDW AI Hub（Python/FastAPI）
├── ddw-personnel-qual（插件1）
├── ddw-bid-writer（插件2）
├── ddw-cost-knowledge（插件3）
├── ddw-llm-gateway（LLM 统一网关）
├── ddw-email-assistant（邮件通知，可选）
└── ddw-adapter-dingtalk/feishu/wecom（IM 适配器，可选）

本地 LLM（Ollama / llama.cpp）
└── 用于知识库提炼、标书生成、人员匹配等 AI 功能

数据库：SQLite（轻量级）或 PostgreSQL（企业级）
存储：本地文件系统（造价文件、标书文件）
```

### 6.1 最低部署要求
- CPU：2 核
- 内存：8 GB（含本地 LLM）
- 磁盘：50 GB
- 网络：仅内网（无公网需求）

### 6.2 推荐部署要求
- CPU：4 核
- 内存：16 GB
- 磁盘：200 GB SSD
- 本地 LLM：7B-14B 参数模型

---

## 七、开发计划

### 7.1 开发顺序

| 阶段 | 插件 | 预计工期 | 前置条件 |
|------|------|---------|---------|
| Phase 1 | ddw-personnel-qual | 3-5 天 | 无 |
| Phase 2 | ddw-cost-knowledge | 5-7 天 | 无（可与 Phase 1 并行） |
| Phase 3 | ddw-bid-writer | 7-10 天 | Phase 1 + Phase 2 完成 |
| Phase 4 | 集成测试 | 2-3 天 | Phase 3 完成 |
| Phase 5 | 客户试点 | 1-2 周 | Phase 4 完成 |

### 7.2 技术栈
- 后端：Python 3.11+ / FastAPI / SQLAlchemy 2.0
- 前端：HTML/CSS/JS（Ant Design 企业 OA 风格）
- LLM：通过 DDW LLM Gateway 统一管理
- OCR：PaddleOCR（本地部署）或 Tesseract
- 文档处理：python-docx（Word 生成）、openpyxl（Excel 读写）、PyMuPDF（PDF 解析）

---

## 八、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 造价文件格式多样，提取准确率不足 | 知识库质量 | 提供手动修正功能，持续优化提取规则 |
| 本地 LLM 生成质量不如云端 | 标书质量 | 支持配置云端 LLM 作为备选 |
| 设计院 IT 基础设施差 | 部署困难 | 提供一键安装脚本 + 远程技术支持 |
| "投标修饰"功能被误解为违法工具 | 声誉风险 | 功能命名中性化，不提及"围标"等敏感词 |
| 住建部政策变化 | 资质管理规则变化 | 预警规则可配置，快速适配 |

---

## 九、验收标准

### 9.1 功能验收
- [ ] 人员资质管理：支持全部证书类型，导入 100 条记录 < 30 秒
- [ ] 到期预警：提前 90/60/30/7 天分级提醒
- [ ] 投标人员匹配：输入资质要求，30 秒内返回匹配结果
- [ ] 招标文件解析：100 页 PDF 解析 < 2 分钟
- [ ] 标书生成：完整技术标生成 < 10 分钟
- [ ] 多风格差异化：生成 3 个差异化版本 < 15 分钟
- [ ] 造价知识库导入：100 个 Excel 文件提炼 < 30 分钟
- [ ] 造价查询：自然语言查询 < 5 秒响应

### 9.2 性能验收
- [ ] API 响应时间 P95 < 3 秒（不含 LLM 生成）
- [ ] 并发 10 用户无崩溃
- [ ] 内存占用 < 500 MB（正常使用场景）

### 9.3 安全验收
- [ ] 人员身份证号加密存储
- [ ] API Key 不出现在日志中
- [ ] 文件上传有大小限制和类型检查

---

*PRD 生成：MiMo-V2.5（xiaomi）· 2026-08-02*
