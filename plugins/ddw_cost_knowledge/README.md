# DDW 造价知识库

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-1.0.0-green.svg)](manifest.yaml)
[![DDW](https://img.shields.io/badge/DDW-AI%20Hub-orange.svg)](#)

设计院历史造价文件 + 定额 / 清单 / 指标的统一管理——文件上传、LLM 提炼、自然语言检索、基于历史数据的造价估算与置信度评估。

## 功能特性

- **造价文件上传**：支持元数据模式（仅录字段）和二进制模式（base64 编码入库），自动落盘到配置的上传目录
- **LLM 提炼**：基于规则的结构化指标抽取（规模 / 单方造价 / 造价档位 / 关键词），预留 LLM 钩子可走 DDW LLM Gateway 进一步润色
- **自然语言检索**：中英文混合打分（英文按词、中文按 2 字 bigram），可按项目类型 / 文件类型过滤
- **造价估算**：基于历史项目（加权中位数 + 25/75 分位 + 结构类型修正系数），自动计算置信度（样本数 + 离散度）
- **指标统计**：文档总数、按文件类型 / 项目类型分布、平均单方造价 / 总造价
- **批量导入**：JSON 列表一次导入多条记录
- **多租户支持**：基于 `tenant_id` 的数据隔离

## 快速开始

### 1. 安装

将 `ddw_cost_knowledge` 目录复制到 DDW AI Hub 的 `plugins/` 目录下。

### 2. 启动

DDW AI Hub 启动时自动加载。插件注册路径：

```
/api/v1/plugins/ddw-cost-knowledge/
```

### 3. API 示例

```bash
# 上传造价文件（仅元数据）
curl -X POST http://localhost:8500/api/v1/plugins/ddw-cost-knowledge/documents/upload \
  -H "Content-Type: application/json" \
  -d '{
    "file_name": "光谷A住宅-2024.pdf",
    "doc_type": "历史造价文件",
    "project_name": "光谷A住宅",
    "project_type": "住宅",
    "area": 50000,
    "total_cost": 175000000
  }'

# 自然语言检索
curl "http://localhost:8500/api/v1/plugins/ddw-cost-knowledge/search?q=住宅%20框剪%203500"

# 创建造价估算
curl -X POST http://localhost:8500/api/v1/plugins/ddw-cost-knowledge/estimates \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "光谷D新住宅",
    "project_type": "住宅",
    "area": 25000,
    "floor_count": 18,
    "structure_type": "框剪"
  }'

# 统计概览
curl http://localhost:8500/api/v1/plugins/ddw-cost-knowledge/stats
```

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/documents/upload` | 上传造价文件 |
| GET | `/documents` | 文件列表（分页 + 筛选） |
| GET | `/documents/{id}` | 文件详情 |
| DELETE | `/documents/{id}` | 删除文件（含磁盘文件） |
| POST | `/documents/{id}/extract` | 触发 LLM 提炼 |
| GET | `/search` | 自然语言检索 |
| POST | `/estimates` | 创建造价估算 |
| GET | `/estimates/{id}` | 估算详情 |
| GET | `/stats` | 统计概览 |
| POST | `/batch-import` | 批量导入（JSON 列表） |

## 数据模型

| 表 | 说明 |
|----|------|
| `cost_documents` | 造价文件主表（文件名、类型、项目、面积、总造价、单方造价、LLM 提炼数据、状态） |
| `cost_estimates` | 造价估算记录（项目类型、面积、层数、结构类型、估算结果、参考文档、置信度） |

## 配置项

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `upload_dir` | `./data/uploads/cost` | 文件上传落盘目录 |
| `default_tenant_id` | `1` | 单租户模式默认 `tenant_id` |
| `estimate_similarity_threshold` | `0.6` | 估算时历史项目相似度阈值 |
| `max_search_results` | `20` | 检索最大返回条数 |

## LLM 对接

本插件的 `extract` / `estimate` 等能力通过 **DDW LLM Gateway** 统一调度。LLM 相关的 API Key、Provider 配置、模型选择等由 DDW 平台统一管理，**插件代码中不包含任何凭证信息**。

如需启用 LLM 提炼：在 `config/deployment.yaml` 中配置 LLM Gateway 即可，无需修改插件代码。

## 技术栈

- Python 3.11+
- FastAPI
- SQLAlchemy 2.0（async）
- SQLite / PostgreSQL
- pytest 8.0+

## 开发与测试

```bash
# 语法检查
python3 -c "import ast; ast.parse(open('router.py').read())"

# 跑测试
python3 -m pytest tests/ -v

# 验证 manifest
python3 -c "import yaml; yaml.safe_load(open('manifest.yaml'))"
```

## License

Apache License 2.0 — 详见 [LICENSE](LICENSE)
