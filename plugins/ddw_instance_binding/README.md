# DDW 实例绑定插件（ddw-instance-binding v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P4-3** —— 把客户企业 / 许可证与运行时实例（云端 SaaS 租户或本地 On-Premise 部署）建立关联。

## 功能描述

- **两类实例**：`saas`（云端 SaaS 租户）/ `on-premise`（本地 On-Premise 部署）
- **关联关系**：实例挂靠到客户企业 + 许可证
- **状态机**：`active` / `inactive` / `suspended`，软删除走 `suspended` 保留审计链
- **心跳上报**：`POST /instances/{id}/heartbeat` 客户端定时上报，平台侧记录 `last_heartbeat`
- **环境标签**：`production` / `staging` / `test`
- **多维筛选**：按企业 / 许可证 / 类型 / 环境 / 状态筛选
- **多租户隔离**：基于 `tenant_id` 的数据隔离

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /instances | 新建实例绑定 |
| GET | /instances | 实例列表（分页 + 多维筛选） |
| GET | /instances/stats | 统计概览 |
| GET | /instances/{id} | 实例详情 |
| PUT | /instances/{id} | 更新实例 |
| DELETE | /instances/{id} | 软删除（status=suspended） |
| POST | /instances/{id}/heartbeat | 心跳上报 |

## 数据模型

`Instance` 表（`crm_instances`）核心字段：

- **主键**：`id` (BigInt)
- **租户**：`tenant_id` (来自 `TenantMixin`)
- **关联**：`company_id` (FK → crm_companies.id, ON DELETE CASCADE) / `license_id` (FK → crm_licenses.id, nullable)
- **类型**：`instance_type` (saas/on-premise) / `instance_id` (外部实例 ID) / `instance_name`
- **指纹**：`fingerprint` (实例指纹，用于防伪)
- **环境**：`environment` (production/staging/test)
- **访问**：`endpoint` (访问地址)
- **状态**：`status` (active/inactive/suspended) / `last_heartbeat` (时间戳)
- **审计**：`created_at` / `updated_at` (来自 `TimestampMixin`)

## 安装方法

插件随 DDW AI Hub 平台一起发布，无需独立安装。

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| default_tenant_id | int | 1 | 默认租户 |
| default_page_size | int | 20 | 列表默认分页大小 |
| instance_types | array | [saas, on-premise] | 实例类型枚举 |
| environments | array | [production, staging, test] | 部署环境枚举 |
| statuses | array | [active, inactive, suspended] | 状态枚举 |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_instance_binding/tests/ -v --tb=short
```

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户
- `core.database.models.TimestampMixin` —— 时间戳
- `core.database.tenant_filter.bypass_tenant_filter` —— 绕过租户过滤
- `sdk.plugin_base.PluginBase` —— 插件基类
- `plugins.ddw_company_profile` / `plugins.ddw_license_core` —— 软依赖

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
