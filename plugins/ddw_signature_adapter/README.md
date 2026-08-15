# DDW 电子签章适配器插件（ddw-signature-adapter v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P5-1** —— 电子签章服务适配层。对接腾讯电子签 / 契约锁 / e签宝 / 人工签等第三方电子签章服务商。

## 功能描述

- **多 Provider 抽象**：支持 `tencent`（腾讯电子签）/ `dianxiaoyu`（契约锁）/ `esign`（e签宝）/ `manual`（人工签）
- **签署请求生命周期**：`pending` → `signing` → `signed` / `rejected` / `expired`
- **第三方异步回调**：`POST /signature-requests/{id}/callback` 接收 provider 回调并更新状态
- **人工上传签后文件**：`POST /signature-requests/{id}/manual-upload` 支持人工补传签后 PDF
- **适配器预留**：各 provider 的实际 HTTP 接入逻辑通过适配器模式扩展（默认 stub）
- **关联合同**：`contract_id` (FK → crm_contracts.id, ON DELETE CASCADE)
- **多租户隔离**：基于 `tenant_id` 的数据隔离

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /signature-requests | 新建签署请求（不真正调第三方） |
| GET | /signature-requests | 列表（分页 + 筛选） |
| GET | /signature-requests/stats | 统计概览 |
| GET | /signature-requests/{id} | 签署请求详情 |
| PUT | /signature-requests/{id} | 更新签署请求（仅 pending 状态） |
| POST | /signature-requests/{id}/callback | 第三方异步回调 |
| POST | /signature-requests/{id}/manual-upload | 人工上传签后文件 |

## 数据模型

`SignatureRequest` 表（`crm_signature_requests`）核心字段：

- **主键**：`id` (BigInt)
- **租户**：`tenant_id` (来自 `TenantMixin`)
- **关联**：`contract_id` (FK → crm_contracts.id, ON DELETE CASCADE)
- **服务商**：`provider` (tencent/dianxiaoyu/esign/manual) / `external_request_id`
- **签署方**：`signers` (JSON 列表)
- **文档**：`document_url` (待签文档) / `signed_document_url` (签后文档)
- **状态**：`status` (pending/signing/signed/rejected/expired) / `signed_at`
- **审计**：`created_at` (来自 `TimestampMixin`)

## 安装方法

插件随 DDW AI Hub 平台一起发布，无需独立安装。

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| default_tenant_id | int | 1 | 默认租户 |
| default_page_size | int | 20 | 列表默认分页大小 |
| providers | array | [tencent, dianxiaoyu, esign, manual] | 支持的电子签章服务商 |
| statuses | array | [pending, signing, signed, rejected, expired] | 签署请求状态枚举 |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_signature_adapter/tests/ -v --tb=short
```

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户
- `core.database.models.TimestampMixin` —— 时间戳
- `core.database.tenant_filter.bypass_tenant_filter` —— 绕过租户过滤
- `sdk.plugin_base.PluginBase` —— 插件基类
- `plugins.ddw_contract_core` —— 必依赖

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
