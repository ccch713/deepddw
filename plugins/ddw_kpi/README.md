# DDW KPI Plugin v0.1.0

企业培训 KPI 考核。企业场景（C/D）专用。

## 能力

- KPI 规则管理（按学科 / 部门 / 权重 / 阈值）
- KPI 计算（加权 + 通过阈值）
- 部门排行 + 个人明细
- 看板数据

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/rules` | 规则列表/创建 |
| GET/PUT/DELETE | `/rules/{id}` | 规则详情/更新/删除 |
| GET | `/dashboard` | KPI 看板 |
| GET | `/employee/{id}` | 员工 KPI 明细 |

## 事件订阅

- `training.assessment.completed` → 触发员工 KPI 重算

## KPI 计算公式

```
score = sum(weighted_scores) / sum(weights)
status = "passed" if score >= threshold else "failed"
```

## 数据模型

- `ddw_kpi_rules`（规则定义：name, subject, weight, threshold, formula, enabled）
- `ddw_kpi_records`（记录：employee_id, rule_id, period, score, status）

## 测试

```bash
pytest plugins/ddw_kpi/tests/ -v
# 8/8 passed
```
