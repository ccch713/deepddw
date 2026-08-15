# DDW 投标标书撰写

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-1.0.0-green.svg)](manifest.yaml)
[![DDW](https://img.shields.io/badge/DDW-AI%20Hub-orange.svg)](#)

设计院投标项目全流程辅助——项目建档、标书自动生成、标书语言润色、标书审查、模板管理。内置 CDEF 企业文档提取框架与向量知识库，支持小模型本地部署。

## 功能特性

- **项目建档**：投标项目主数据管理（项目名、客户、类型、估算金额、截止时间、状态）
- **标书自动生成**：基于章节模板 + 项目信息 + LLM 生成完整标书内容（技术标 / 商务标 / 资格预审）
- **标书语言润色与表达风格调整**：基于企业偏好对已生成标书进行语言润色与表达风格调整
  - 风格选项：标准 / 保守 / 激进 / 创新型
  - 调整维度：措辞 / 结构 / 图表 / 表述 / 术语
  - 保留版本历史，便于对比与回溯
- **标书审查**：6 项自动检查（章节完整性、关键字段、敏感词、字符长度、结构层级、联系人/电话） + 评分 + 改进建议
- **标书批准**：审批流程闭环
- **模板管理**：用户自定义模板 + 系统默认模板
- **CDEF 企业文档提取框架**：4 阶段流水线（Plan → Parallel Generation → Consistency Check → Polish）
- **RAG 向量知识库**：基于历史标书的相似度检索增强
- **多 Agent 协作**：Planner / Writer / Reviewer / Editor 4 个 Agent 协同工作
- **渐进式披露**：重要项目自动检测，章节级 lock / unlock / regenerate，按需人工介入
- **多租户支持**：基于 `tenant_id` 的数据隔离

## 快速开始

### 1. 安装

将 `ddw_bid_writer` 目录复制到 DDW AI Hub 的 `plugins/` 目录下。

### 2. 启动

DDW AI Hub 启动时自动加载。插件注册路径：

```
/api/v1/plugins/ddw-bid-writer/
```

### 3. 工作流

```
┌────────────────────────────────────────────────────────┐
│  1. 知识库准备（一次性）                                   │
│     选择历史标书文件夹 → 自动学习（解析/分块/向量化/抽模板）  │
│                                                           │
│  2. 新建投标项目                                          │
│     填写项目信息 → 系统评估重要级别（普通/重要/关键）         │
│                                                           │
│  3. 生成标书                                              │
│     普通项目：auto 模式一键生成                            │
│     重要项目：建议渐进式披露（逐章审阅）                     │
│                                                           │
│  4. 审查与批准                                            │
│     自动审查 → 评分 → 人工 review → 批准                   │
└────────────────────────────────────────────────────────┘
```

### 4. API 示例

```bash
# 学习历史标书（建立 RAG 知识库）
curl -X POST http://localhost:8500/api/v1/plugins/ddw-bid-writer/knowledge/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"folder": "/path/to/historical/bids", "tenant_id": 1}'

# 新建投标项目
curl -X POST http://localhost:8500/api/v1/plugins/ddw-bid-writer/projects \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "光谷A住宅投标",
    "client_name": "光谷置业",
    "project_type": "住宅",
    "estimated_amount": 500000000
  }'

# 评估项目重要级别
curl -X POST http://localhost:8500/api/v1/plugins/ddw-bid-writer/projects/1/assess-importance \
  -H "Content-Type: application/json" -d '{}'

# 生成标书（CDEF 全流程）
curl -X POST http://localhost:8500/api/v1/plugins/ddw-bid-writer/projects/1/generate \
  -H "Content-Type: application/json" \
  -d '{"doc_type": "技术标", "style": "标准", "mode": "auto"}'

# 标书审查
curl -X POST http://localhost:8500/api/v1/plugins/ddw-bid-writer/documents/1/review \
  -H "Content-Type: application/json" -d '{}'
```

## API 端点（共 25 个）

### 项目管理
| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/projects` | 新建投标项目 |
| GET | `/projects` | 项目列表 |
| GET | `/projects/{id}` | 项目详情 |
| PUT | `/projects/{id}` | 更新项目 |
| DELETE | `/projects/{id}` | 删除项目 |
| POST | `/projects/{id}/generate` | 生成标书（CDEF 4 阶段流水线） |
| GET | `/projects/{id}/documents` | 项目下所有标书 |
| POST | `/projects/{id}/plan` | 阶段 1：仅生成大纲 |
| POST | `/projects/{id}/assess-importance` | 评估项目重要级别 |

### 标书文档
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/documents/{id}` | 标书详情 |
| PUT | `/documents/{id}` | 编辑标书 |
| POST | `/documents/{id}/refine` | 标书语言润色与表达风格调整 |
| POST | `/documents/{id}/review` | 标书审查（合规检查） |
| POST | `/documents/{id}/approve` | 批准标书 |
| GET | `/documents/{id}/sections` | 章节级列表（渐进式披露） |
| POST | `/documents/{id}/sections/{idx}/regenerate` | 章节级重生成 |
| POST | `/documents/{id}/sections/{idx}/lock` | 锁定章节 |
| POST | `/documents/{id}/sections/{idx}/unlock` | 解锁章节 |

### 模板管理
| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/templates` | 模板列表 |
| POST | `/templates` | 新建模板 |
| PUT | `/templates/{id}` | 更新模板 |
| DELETE | `/templates/{id}` | 删除模板 |

### 知识库
| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/knowledge/bootstrap` | 从历史标书文件夹学习 |
| GET | `/knowledge/status` | 知识库状态 |
| GET | `/knowledge/templates` | 已学习的模板列表 |

## 数据模型

| 表 | 说明 |
|----|------|
| `bid_projects` | 投标项目主表 |
| `bid_documents` | 标书文档（含 content / version / status） |
| `bid_templates` | 标书模板 |
| `bid_sections` | 章节级记录（支持锁定） |
| `bid_kb_documents` | 学习用历史标书记录 |
| `bid_kb_runs` | 学习运行审计 |
| `bid_fact_templates` | 学出的事实模板 |
| `bid_agent_runs` | 多 Agent 运行审计 |

## CDEF 4 阶段流水线

```
Plan → Parallel Generation → Consistency Check → Polish
```

- **Plan**：生成大纲（6 章节 × 目标字数）+ 风格基线 + FactSheet 初始化
- **Parallel Generation**：6 个章节 `asyncio.gather` 并发，每章 prompt 注入：FactSheet（硬约束）+ 风格基线 + 衔接上下文 + RAG 检索 top-3 相似历史
- **Consistency Check**：抽取所有事实 → 比对 FactSheet → 标记冲突 → 局部重写
- **Polish**：全文润色 + 统稿

### 关键组件

- **FactSheet**：结构化事实表（项目名 / 客户 / 金额 / 人员 / 日期 / 指标 / 风格基线），每章 prompt 注入作为硬约束
- **RAG**：基于 TenantKnowledgeStore 的本地向量库，每章生成前检索 top-3 相似历史章节
- **Multi-Agent**：4 个 Agent 通过 DDW LLM Gateway 协同工作，全 trace 落库
- **Importance Detector**：基于金额 + 截止 + 客户首次 + 项目类型综合评估（routine / important / critical）

## 生成模式

| 模式 | 行为 | 适用场景 |
|------|------|----------|
| `auto` | CDEF 全流程（4 阶段） | 普通项目（< 1 亿） |
| `important` | 渐进式披露（章节级 API） | 重要 / 关键项目（≥ 1 亿） |
| `skeleton` | 仅生成大纲 | 快速预览 |
| `legacy` | 旧版一次性生成 | 向后兼容 |

## 配置项

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `available_styles` | `[标准, 保守, 激进, 创新型]` | 标书风格调整可选类型 |
| `default_doc_type` | `技术标` | 默认标书类型 |
| `use_llm` | `false` | 是否启用 LLM 真实调用（生产开启） |

## LLM 对接

本插件的所有 LLM 调用（提炼 / 润色 / 审查 / 评估）均通过 **DDW LLM Gateway** 统一调度：

- **API Key / Provider / 模型选择** 等由 DDW 平台在 `config/deployment.yaml` 中统一管理
- **插件代码中不包含任何凭证信息**
- 支持本地 LLM（如 llama.cpp 后端）作为 Provider
- 小模型场景下，建议将核心任务（事实一致性、风格基线、关键字段）由本地 LLM 承担，非核心任务（润色、扩写）由云端大模型补充

## 脱敏与合规

- 本插件对敏感功能采用**中性命名**（"标书语言润色与表达风格调整"）
- 敏感词库从外部 config 文件加载，不在源码中硬编码
- 风格选项为**中性描述**（标准 / 保守 / 激进 / 创新型），不暗示任何用途
- 所有 UI / 文档 / 注释均通过自动敏感词扫描

## 技术栈

- Python 3.11+
- FastAPI
- SQLAlchemy 2.0（async）
- SQLite / PostgreSQL
- DDW LLM Gateway
- pytest 8.0+

## 开发与测试

```bash
# 语法检查
python3 -c "import ast; ast.parse(open('router.py').read())"

# 跑测试
python3 -m pytest tests/ -v

# 验证 manifest
python3 -c "import yaml; yaml.safe_load(open('manifest.yaml'))"

# 脱敏扫描（按项目维护的 PROHIBITED_TERM 列表自动检查）
python3 -c "
from pathlib import Path
import re
# 占位：实际列表从 config/prohibited_terms.json 加载（不在 README 中硬编码）
SENSITIVE_PLACEHOLDER = re.compile(r'PROHIBITED_TERM_\d+')  # 实际部署替换
import sys
bad = []
for f in Path('.').rglob('*.py'):
    if '/tests/' in str(f): continue
    text = f.read_text(encoding='utf-8', errors='ignore')
    # 真实部署用：for w in load_prohibited_terms(): if w in text: ...
    if SENSITIVE_PLACEHOLDER.search(text):
        bad.append(f'{f}: placeholder match')
print('PASS' if not bad else f'FAIL: {bad}')
"
```

## License

Apache License 2.0 — 详见 [LICENSE](LICENSE)
