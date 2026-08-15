# ddw-org — DDW AI 组织插件

管理企业虚拟部门架构：11 个预设部门、数字员工、员工清单。

## 功能

- **部门管理**：11 个预设虚拟部门，可改名称/介绍
- **数字员工**：每个部门预设 1 个数字员工，可配名称/技能
- **员工管理**：企业真实员工清单，手动添加/编辑/删除
- **Skill 池**：数字员工可分配/移除技能

## API

| Method | Path | 说明 |
|--------|------|------|
| GET | /api/v1/org/departments | 部门列表 |
| GET | /api/v1/org/departments/{id} | 部门详情 |
| PUT | /api/v1/org/departments/{id} | 修改部门 |
| POST | /api/v1/org/departments | 新建部门 |
| GET | /api/v1/org/agents | 数字员工列表 |
| GET | /api/v1/org/agents/{id} | 数字员工详情 |
| PUT | /api/v1/org/agents/{id} | 修改数字员工 |
| POST | /api/v1/org/agents/{id}/skills | 分配 skill |
| DELETE | /api/v1/org/agents/{id}/skills/{skill_id} | 移除 skill |
| GET | /api/v1/org/employees | 员工列表 |
| POST | /api/v1/org/employees | 新增员工 |
| PUT | /api/v1/org/employees/{id} | 修改员工 |
| DELETE | /api/v1/org/employees/{id} | 删除员工 |
| GET | /api/v1/org/skills | Skill 池列表 |
| POST | /api/v1/org/seed | 触发种子数据 |
| GET | /api/v1/org/health | 健康检查 |

## 种子数据

`POST /api/v1/org/seed` 幂等创建 11 个部门 + 11 个数字员工 + 21 个 Skill。

## 外部调用

```python
from plugins.ddw_org.plugin import seed_for_tenant
result = await seed_for_tenant(tenant_id=1)
```
