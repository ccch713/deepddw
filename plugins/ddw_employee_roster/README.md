# DDW Employee Roster Plugin v0.1.0

企业员工花名册 + 培训档案。企业场景（C/D）专用。

## 能力

- 员工 CRUD（增删改查）
- 培训档案（自动从 training.session.completed 同步）
- 部门聚合（按部门统计人数）
- 批量导入（待实现）

## API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/employees` | 员工列表/创建 |
| GET/PUT/DELETE | `/employees/{id}` | 员工详情/更新/删除 |
| GET | `/employees/{id}/training` | 员工培训档案 |
| GET | `/departments` | 部门列表 |

## 事件订阅

- `training.session.completed` → 写入 `ddw_employee_training_records`
- `training.assessment.completed` → 更新分数字段

## 数据模型

- `ddw_employees`（员工基本信息）
- `ddw_employee_training_records`（员工培训记录）

## HRIS 集成

通过 `core/hris_adapters/` 平台底座，支持：
- 北森 / 用友 / 金蝶 / 钉钉 / 飞书 / 企业微信
- SAP SuccessFactors / Oracle HCM / Workday

## 测试

```bash
pytest plugins/ddw_employee_roster/tests/ -v
# 4/4 passed
```
