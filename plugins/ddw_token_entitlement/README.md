# DDW Token 额度管理插件（ddw-token-entitlement v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P4-4** —— 客户企业 / 安装实例的 Token 额度分配、使用跟踪与超量控制。

## 功能描述

- **三类额度**：`platform`（平台分配）/ `custom-key`（客户自带 Key）/ `local-llm`（本地 LLM）
- **额度分配**：客户企业 / 安装实例维度设置总配额
- **消耗扣减**：`POST /entitlements/{id}/consume` 调用即扣减；超量时若 `overage_allowed=true` 允许透支
- **客户 Key 脱敏存储**：`api_key_masked` 只存脱敏串，原 Key 由客户自带不入库
- **本地 LLM 地址**：`llm_endpoint` 记录本地 LLM 服务的访问地址
- **多租户隔离**：基于 `tenant_id` 的数据隔离

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /entitlements | 分配额度 |
| GET | /entitlements | 列表（分页 + 筛选） |
| GET | /entitlements/stats | 统计概览 |
| GET | /entitlements/{id} | 额度详情 |
| PUT | /entitlements/{id} | 更新额度 |
| DELETE | /entitlements/{id} | 删除额度（硬删除） |
| POST | /entitlements/{id}/consume | 消耗 tokens |

## 数据模型

`TokenEntitlement` 表（`crm_token_entitlements`）核心字段：

- **主键**：`id` (BigInt)
- **租户**：`tenant_id` (来自 `TenantMixin`)
- **关联**：`company_id` (FK → crm_companies.id, ON DELETE CASCADE) / `instance_id` (FK → crm_instances.id, nullable)
- **类型**：`entitlement_type` (platform/custom-key/local-llm)
- **配额**：`allocated_tokens` / `used_tokens`
- **超量控制**：`overage_allowed` (bool)
- **凭据**：`api_key_masked` (脱敏 Key) / `llm_endpoint` (本地 LLM 地址)
- **审计**：`created_at` / `updated_at` (来自 `TimestampMixin`)

## 安装方法

插件随 DDW AI Hub 平台一起发布，无需独立安装。

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| default_tenant_id | int | 1 | 默认租户 |
| default_page_size | int | 20 | 列表默认分页大小 |
| entitlement_types | array | [platform, custom-key, local-llm] | 额度类型枚举 |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_token_entitlement/tests/ -v --tb=short
```

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户
- `core.database.models.TimestampMixin` —— 时间戳
- `core.database.tenant_filter.bypass_tenant_filter` —— 绕过租户过滤
- `sdk.plugin_base.PluginBase` —— 插件基类

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
