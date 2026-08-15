# DDW Token Manager Plugin

> **版本**: 0.1.0 | **状态**: 开发中
>
> 基于 One API (songquanpeng/one-api) 额度管理系统，为 DDW AI Hub 提供 Token 额度管理能力。

## 功能特性

### 核心功能

| 功能 | 对应 One API 源码 | 说明 |
|------|------------------|------|
| **预消费机制** | `relay/controller/helper.go:L68-95` | 请求前预扣额度，防止超用 |
| **后消费补偿** | `relay/controller/helper.go:L97-141` | 实际消耗后补偿差额 |
| **额度退还** | helper.go 失败回滚路径 | 请求失败时退还预扣额度 |
| **高信任跳过** | `helper.go:L82-87` | 用户额度 > 100×预扣时跳过 Token 预扣 |
| **最小消耗保证** | `helper.go:L107-109` | quota ≤ 0 时设为 1 |
| **模型倍率系统** | `relay/billing/ratio/model.go` | 569 个模型的输入/输出倍率 |
| **批量更新** | `model/utils.go` | asyncio.Lock + defaultdict 内存队列 |

### DDW 独有功能

| 功能 | 说明 |
|------|------|
| **校准反算** | 基于 Provider 实际账单反算校准系数 K |
| **订阅感知** | 企业客户订阅信息管理 + 低余额预警 |
| **深度思考模型** | DeepSeek Reasoner 等输出倍率特殊处理 |

## 目录结构

```
ddw-token-manager/
├── manifest.yaml           # 插件元数据
├── README.md               # 本文件
├── requirements.txt        # Python 依赖
├── __init__.py             # 包入口
├── main.py                 # 插件入口，DDWPlugin 子类
├── models.py               # SQLAlchemy 数据模型
├── quota.py                # 预消费/后消费核心算法
├── calibration.py          # 校准反算算法
├── router.py               # FastAPI 路由 (10 个端点)
├── config_loader.py        # 倍率配置加载（569 模型）
├── tests/
│   ├── __init__.py
│   ├── test_quota.py       # 消费流程单元测试
│   └── test_calibration.py # 校准算法单元测试
└── config/
    └── model_ratios.yaml   # 模型倍率 (symlink → DDW 主配置)
```

## 快速开始

### 安装依赖

```bash
cd plugins/ddw-token-manager
pip install -r requirements.txt
```

### 运行测试

```bash
cd plugins/ddw-token-manager
pytest tests/ -v
```

### API 端点

所有路由挂载在 `/api/v1/plugins/ddw-token-manager/` 下:

#### 额度管理
- `POST /quota/pre-consume` — 预消费额度
- `POST /quota/post-consume` — 后消费 + 差额补偿
- `POST /quota/return` — 退还预消费额度
- `GET /quota/balance/{user_id}` — 查询余额

#### 校准管理
- `POST /calibration/register` — 登记订阅信息
- `POST /calibration/update` — 更新实际用量
- `GET /calibration/status/{provider}` — 校准状态

#### 成本统计
- `GET /cost/realtime?minutes=5` — 实时成本
- `GET /cost/daily?date=2026-07-13` — 日成本统计
- `GET /cost/by-model?days=7` — 按模型统计

#### 倍率查询
- `GET /ratio/model/{model_name}` — 查询模型倍率
- `GET /ratio/group/{group_name}` — 查询分组倍率
- `GET /ratio/models` — 列出所有模型

## 消费流程

```
请求进入
  │
  ├── pre_consume_quota()
  │   ├── 计算预消费额度 = (基础额度 + promptTokens + maxTokens) × ratio
  │   ├── 检查用户额度是否充足
  │   ├── 高额用户跳过 Token 预扣（信任机制）
  │   └── 预扣 Token 额度
  │
  ├── [执行 API 请求]
  │
  └── post_consume_quota()
      ├── 计算实际 quota = ceil((prompt + completion × completionRatio) × modelRatio × groupRatio)
      ├── 差额补偿 = quota - preConsumedQuota
      └── 记录消费日志
```

## 校准反算

```
企业客户登记订阅 → 记录实际用量 → 计算校准系数 K
                                      │
                              K = Σ(actual) / Σ(estimated)
                                      │
                              连续两次 K 变化 < 5% → 收敛
```

## 技术栈

- Python 3.11+
- FastAPI
- SQLAlchemy 2.0 (async)
- Pydantic v2
- PyYAML
- pytest + pytest-asyncio

## 相关文档

- [MiMo 分析报告](../../Documents/Obsidian/03_项目/DDW_AI_Hub/One_API分析/one-api-ddw-adaptation-blueprint-mimo.md)
- [DDW 插件开发指南](../../docs/DDW_Plugin_Development_Guide.md)
- [One API 源码](https://github.com/songquanpeng/one-api)
