# DDW 客户报备与归属插件（ddw-lead-claim v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P2-2** —— 客户报备、保护期、冲突裁定、释放。

## 功能描述

- **报备登记**：渠道伙伴对目标客户做报备，自动计算 `expire_at = claim_date + protection_days`
- **保护期**：默认 60 天，保护期内同一渠道对同一客户不可重复报备
- **冲突裁定**：当多渠道对同一客户做报备时，按"首次报备 + 最近 30 天跟进证据"裁定
- **保护期满自动释放**：`status='expired'` 由 `_auto_mark_expired()` 在 list/get 前自动更新
- **主动释放**：`/release` 端点主动释放报备
- **多租户隔离**：基于 `tenant_id` 的数据隔离

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /claims | 新建报备（自动计算 expire_at） |
| GET | /claims | 列表（分页 + 多维筛选） |
| GET | /claims/{id} | 报备详情 |
| PUT | /claims/{id} | 更新（仅 active 状态） |
| POST | /claims/{id}/release | 主动释放 |
| GET | /claims/conflict | 冲突查询（入参 company_id） |
| GET | /claims/stats | 统计概览 |

## 业务规则

1. **同一 partner 对同一 company 只允许 1 个 active 报备**（防重复占位）
2. **expire_at = claim_date + protection_days**（服务端计算，不取调用方）
3. **保护期满自动标记 expired**（list/stats 前批量更新）
4. **释放后 status=released**（记录 release_reason）

## 数据模型

`LeadClaim` 表（`crm_lead_claims`）核心字段：

- **主键**：`id` (BigInt)
- **租户**：`tenant_id` (来自 `TenantMixin`)
- **关联**：`partner_id` (FK → crm_partners.id) / `company_id` (FK → crm_companies.id)
- **报备**：`claim_date` (DateTime) / `protection_days` (Int, 默认 60) / `expire_at` (DateTime)
- **联系人**：`contact_person` / `contact_phone` / `opportunity_source`
- **业务**：`expected_amount` (Numeric(12,2)) / `follow_up_notes` / `last_follow_up_at`
- **状态**：`status` (active/expired/won/lost/released)
- **审计**：`created_at` / `updated_at` (来自 `TimestampMixin`)

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_lead_claim/tests/ -v --tb=short
```

## 依赖

- `core.database.session.Base`
- `core.database.models.TenantMixin` / `TimestampMixin`
- `sdk.plugin_base.PluginBase`

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
