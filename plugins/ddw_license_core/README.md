# DDW 许可证管理插件（ddw-license-core v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P4-2** —— 许可证（License）全生命周期管理。

## 功能描述

- **自动生成单号**：`license_no` (unique, LIC-YYYYMMDD-NNN)
- **三类许可证**：`trial`（试用）/`formal`（正式）/`renewal`（续费）
- **状态机**：`active` / `expired` / `suspended` / `revoked` / `renewed`
- **自动过期检查**：跨日定时任务（或调用方触发）将过期许可证切到 `expired`
- **续费**：`POST /licenses/{id}/renew` 生成新许可证，旧证置 `renewed`
- **暂停/恢复/吊销**：`/suspend` `/resume` `/revoke` 三个端点
- **插件授权清单**：`plugin_entitlements` (JSON) 记录该许可证启用的插件列表
- **多租户隔离**：基于 `tenant_id` 的数据隔离

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /licenses | 新建许可证（自动 license_no） |
| GET | /licenses | 列表（分页 + 筛选：type/status/company） |
| GET | /licenses/stats | 统计概览 |
| GET | /licenses/{id} | 许可证详情 |
| PUT | /licenses/{id} | 更新许可证 |
| POST | /licenses/{id}/renew | 续费（生成新证 + 旧证置 renewed） |
| POST | /licenses/{id}/suspend | 暂停 |
| POST | /licenses/{id}/resume | 恢复（suspended → active） |
| POST | /licenses/{id}/revoke | 吊销（active → revoked） |

## 数据模型

`License` 表（`crm_licenses`）核心字段：

- **主键**：`id` (BigInt)
- **单号**：`license_no` (unique)
- **租户**：`tenant_id` (来自 `TenantMixin`)
- **关联**：`company_id` (FK → crm_companies.id, ON DELETE CASCADE)
- **类型**：`license_type` (trial/formal/renewal)
- **范围**：`product_ids` (JSON list) / `plugin_entitlements` (JSON list)
- **容量**：`max_users` / `max_nodes`
- **时效**：`valid_from` / `valid_to` (Date)
- **状态**：`status` (active/expired/suspended/revoked/renewed)
- **审计**：`created_at` / `updated_at` (来自 `TimestampMixin`)

## 安装方法

插件随 DDW AI Hub 平台一起发布，无需独立安装。

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| default_tenant_id | int | 1 | 默认租户 |
| default_page_size | int | 20 | 列表默认分页大小 |
| license_types | array | [trial, formal, renewal] | 许可证类型枚举 |
| statuses | array | [active, expired, suspended, revoked, renewed] | 状态枚举 |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_license_core/tests/ -v --tb=short
```

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户
- `core.database.models.TimestampMixin` —— 时间戳
- `core.database.tenant_filter.bypass_tenant_filter` —— 绕过租户过滤
- `sdk.plugin_base.PluginBase` —— 插件基类
- `plugins.ddw_company_profile` —— 软依赖（外键 crm_companies.id）

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
