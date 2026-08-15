# DDW 账号/租户/实例映射插件（ddw-account-linker v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P5-3** —— 账号映射中枢。把客户企业（crm_companies）映射到下游三类账号：用户（user）、SaaS 租户（saas_tenant）、本地部署实例（on_premise_instance），支撑跨系统账号关联、唯一性校验、生命周期管理。

## 功能描述

- **基础信息**：链接类型（user / saas_tenant / on_premise_instance）、外部 ID、外部名称
- **唯一性**：在 `(tenant_id, link_type, external_id)` 范围内唯一，避免重复绑定
- **关联企业**：可选挂靠 `crm_companies.id`，企业被删/归档后链接保留（ON DELETE SET NULL）
- **扩展字段**：`metadata_json` 存实例规格 / 租户 region / 业务标签等任意 JSON
- **状态机**：`active` / `inactive`，软删除走 `inactive`（保留审计链）
- **多租户隔离**：基于 `tenant_id` 的数据隔离

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /account-links | 新建账号链接 |
| GET | /account-links | 列表（分页 + 筛选：company_id / link_type / status） |
| GET | /account-links/stats | 统计概览（total / active / inactive + by_link_type） |
| GET | /account-links/by-company/{company_id} | 查询某企业的所有链接（不区分状态） |
| GET | /account-links/{id} | 链接详情 |
| DELETE | /account-links/{id} | 软删除（status=inactive） |

注意：`/stats` 与 `/by-company/{cid}` 必须在 `/{id}` 之前注册，否则 FastAPI 会把 `stats` / 字符串解析为 id。

## 数据模型

`AccountLink` 表（`crm_account_links`）核心字段：

- **主键**：`id` (BigInt)
- **租户**：`tenant_id` (来自 `TenantMixin`)
- **关联企业**：`company_id` (FK → crm_companies.id, ON DELETE SET NULL)
- **类型**：`link_type` (user/saas_tenant/on_premise_instance) / `external_id` / `external_name`
- **扩展**：`metadata_json` (JSON dict)
- **状态**：`status` (active/inactive)
- **审计**：`created_at` / `updated_at` (来自 `TimestampMixin`) / `created_by`

## 安装方法

插件随 DDW AI Hub 平台一起发布，无需独立安装。

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| default_tenant_id | int | 1 | 默认租户 |
| default_page_size | int | 20 | 列表默认分页大小 |
| link_types | array | [user, saas_tenant, on_premise_instance] | 链接类型枚举 |
| statuses | array | [active, inactive] | 状态枚举 |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_account_linker/tests/ -v --tb=short
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
