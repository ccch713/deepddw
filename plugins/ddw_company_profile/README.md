# DDW 企业主体管理插件（ddw-company-profile v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P0-1** —— 企业工商主数据管理。

## 功能描述

提供销售侧企业主数据全生命周期管理能力：

- **工商主数据**：工商注册全名、统一社会信用代码（18 位）、企业类型、注册地址、法人、成立日期、经营范围、营业执照附件
- **认证状态**：pending / submitted / approved / rejected / expired（自动记录提交/通过时间戳）
- **开票信息**：发票抬头、税号、开户行、银行账号、公司电话、通讯地址
- **业务字段**：行业、企业规模、注册资本、年营收
- **多维筛选**：按状态、认证状态、企业类型、行业筛选
- **模糊搜索**：按名称/简称/信用代码/法人模糊匹配
- **统计概览**：总数 / 状态分布 / 认证状态分布 / 企业类型分布 / 行业分布
- **多租户隔离**：基于 `tenant_id` 的数据隔离（SQLAlchemy 事件钩子自动注入/过滤）
- **软删除**：`DELETE` 走归档（status=archived），不物理删除

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/companies` | 新建企业 |
| GET | `/companies` | 企业列表（分页 + 筛选 + 搜索） |
| GET | `/companies/search?q=` | 名称/信用代码搜索（自动补全） |
| GET | `/companies/stats` | 统计概览 |
| GET | `/companies/{id}` | 企业详情 |
| PUT | `/companies/{id}` | 更新企业 |
| DELETE | `/companies/{id}` | 归档企业（软删除） |

## 数据模型

`Company` 表（`crm_companies`）核心字段：

- **主键**：`id` (BigInt, 自增)
- **租户**：`tenant_id` (来自 `TenantMixin`，外键 `tenants.id`，ON DELETE CASCADE)
- **工商**：`name` / `credit_code` (唯一) / `short_name` / `company_type` / `registered_address` / `legal_representative` / `established_date` / `business_license_url` / `business_scope`
- **认证**：`certification_status` / `certification_submitted_at` / `certification_approved_at` / `certification_expires_at`
- **开票**：`invoice_title` / `tax_id` / `bank_name` / `bank_account` / `company_phone` / `company_address`
- **业务**：`industry` / `company_size` / `registered_capital` / `annual_revenue`
- **扩展**：`tags` (JSON list) / `notes` / `status` (active/inactive/archived)
- **审计**：`created_at` / `updated_at` (来自 `TimestampMixin`) / `created_by` / `updated_by`

## 安装方法

插件随 DDW AI Hub 平台一起发布。无需独立安装。

开发模式启用：
1. 确保 `plugins/ddw_company_profile/manifest.yaml` 存在
2. 平台启动时 `core/main.py:load_plugins()` 会自动扫描并加载

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `default_tenant_id` | int | 1 | 默认租户 |
| `default_page_size` | int | 20 | 列表默认分页大小 |
| `certification_statuses` | array | `[pending, submitted, approved, rejected, expired]` | 认证状态枚举 |
| `company_types` | array | `[有限公司, 股份公司, 个体工商户, 合伙企业, 国有企业]` | 企业类型枚举 |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_company_profile/tests/ -v --tb=short
```

测试覆盖：
- ✅ 创建（正常 / 重复 credit_code）
- ✅ 列表（分页 / 搜索 / 筛选）
- ✅ 详情（存在 / 不存在）
- ✅ 更新（正常 / 不存在）
- ✅ 归档
- ✅ 搜索自动补全
- ✅ 统计概览

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户
- `core.database.models.TimestampMixin` —— 时间戳
- `core.database.tenant_filter.bypass_tenant_filter` —— 绕过租户过滤（仅限开发/admin）
- `sdk.plugin_base.PluginBase` —— 插件基类

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
