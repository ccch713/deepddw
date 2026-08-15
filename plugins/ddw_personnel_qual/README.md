# DDW 设计人员资质管理

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/Version-1.0.0-green.svg)](manifest.yaml)
[![DDW](https://img.shields.io/badge/DDW-AI%20Hub-orange.svg)](#)

设计院人员证书全生命周期管理插件——录入、查询、批量导入导出、到期预警、年检追踪、统计概览。

## 功能特性

- **证书台账管理**：支持注册建筑师 / 注册结构师 / 注册设备师 / 监理工程师 / 造价工程师 / 咨询工程师 / 一级建造师等全类型证书
- **批量导入导出**：CSV / Excel 批量导入，CSV 导出
- **智能到期预警**：按 30 / 60 / 90 天分级预警，支持自定义提前天数
- **年检追踪**：年检记录全生命周期管理（发起 → 通过 / 失败 → 自动同步证书状态）
- **统计概览**：证书总数 / 有效 / 过期 / 年检中 / 类型分布 / 等级分布一键查看
- **多租户支持**：基于 `tenant_id` 的数据隔离，配合 DDW 平台统一租户管理

## 快速开始

### 1. 安装

将 `ddw_personnel_qual` 目录复制到 DDW AI Hub 的 `plugins/` 目录下即可。

### 2. 启动

DDW AI Hub 启动时会自动扫描 `plugins/` 目录并加载本插件。插件注册路径：

```
/api/v1/plugins/ddw-personnel-qual/
```

### 3. API 示例

```bash
# 新增证书
curl -X POST http://localhost:8500/api/v1/plugins/ddw-personnel-qual/certs \
  -H "Content-Type: application/json" \
  -d '{
    "person_name": "张三",
    "person_id": "ZS001",
    "cert_type": "一级注册结构工程师",
    "cert_no": "S20240001",
    "cert_level": "一级",
    "expiry_date": "2027-12-31"
  }'

# 查询到期预警（30/60/90 天分档）
curl http://localhost:8500/api/v1/plugins/ddw-personnel-qual/expiring

# 统计概览
curl http://localhost:8500/api/v1/plugins/ddw-personnel-qual/stats
```

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/certs` | 新增证书 |
| GET | `/certs` | 证书列表（分页 + 筛选） |
| GET | `/certs/{id}` | 证书详情 |
| PUT | `/certs/{id}` | 更新证书 |
| DELETE | `/certs/{id}` | 删除证书 |
| POST | `/certs/import` | 批量导入（CSV / Excel） |
| GET | `/certs/export` | 导出 CSV |
| GET | `/expiring` | 到期预警列表（30/60/90 天） |
| GET | `/stats` | 统计概览 |
| GET | `/persons/{id}/certs` | 某人所有证书 |
| POST | `/renewals` | 发起年检 |
| PUT | `/renewals/{id}` | 更新年检状态 |
| GET | `/renewals` | 年检记录列表 |
| GET | `/alerts` | 提醒通知列表 |

## 数据模型

| 表 | 说明 |
|----|------|
| `personnel_certs` | 证书主表（人员、类型、编号、等级、发证/到期/年检日期、状态） |
| `cert_renewals` | 年检记录表（关联 cert_id、日期、结果、操作人） |
| `cert_alerts` | 提醒通知表（按到期分档，30/60/90 天） |

所有租户级表继承 `TenantMixin`，由 DDW 平台自动按 `tenant_id` 过滤。

## 配置项

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `expiry_warn_days` | `90` | 到期预警提前天数（可按 30/60/90 分档） |
| `default_tenant_id` | `1` | 单租户模式默认 `tenant_id` |

通过 DDW AI Hub 的配置管理（`config/deployment.yaml` 或管理后台）修改。

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
