# DDW 联系人管理插件（ddw-contact-hub v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P0-2** —— 企业级联系人主数据管理。

## 功能描述

提供销售侧联系人主数据全生命周期管理能力：

- **基本信息**：姓名、职位、部门、手机、邮箱、微信
- **企业关联**：可选 `company_id`（可空，支持独立联系人）；外键 `crm_companies.id` ON DELETE SET NULL
- **主联系人**：`is_primary` 标识（每个企业通常 1 个主联系人）
- **扩展字段**：`tags`（JSON 列表）/ `groups`（JSON 分组）/ `notes`（备注）
- **多维筛选**：按状态、企业、是否主联系人、标签、分组筛选
- **模糊搜索**：按姓名/手机/邮箱/职位/部门模糊匹配；autocomplete 专用端点
- **企业聚合**：`by-company/{company_id}` 返回某企业全部联系人（主联系人优先）
- **统计概览**：总数 / 状态分布 / 主联系人数 / 关联企业 / 独立联系人 / by_company
- **多租户隔离**：基于 `tenant_id` 的数据隔离（SQLAlchemy 事件钩子自动注入/过滤）
- **硬删除**：`DELETE` 走物理删除（任务规范明确，联系人无重要业务依赖）

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/contacts` | 新建联系人 |
| GET | `/contacts` | 联系人列表（分页 + 筛选 + 搜索） |
| GET | `/contacts/search?q=` | 姓名/手机/邮箱搜索（autocomplete） |
| GET | `/contacts/by-company/{company_id}` | 某企业所有联系人 |
| GET | `/contacts/stats` | 统计概览 |
| GET | `/contacts/{id}` | 联系人详情 |
| PUT | `/contacts/{id}` | 更新联系人 |
| DELETE | `/contacts/{id}` | 硬删除联系人 |

## 数据模型

`Contact` 表（`crm_contacts`）核心字段：

- **主键**：`id` (BigInt, 自增)
- **租户**：`tenant_id` (来自 `TenantMixin`，外键 `tenants.id`，ON DELETE CASCADE)
- **关联**：`company_id` (外键 `crm_companies.id`，ON DELETE SET NULL，可空，索引)
- **基本**：`name` (必填，索引) / `phone` (索引) / `email` (索引) / `position` / `department` / `wechat`
- **扩展**：`tags` (JSON list) / `groups` (JSON list) / `is_primary` / `notes`
- **状态**：`status` (active/inactive/archived)
- **审计**：`created_at` / `updated_at` (来自 `TimestampMixin`) / `created_by`

## 安装方法

插件随 DDW AI Hub 平台一起发布。无需独立安装。

开发模式启用：
1. 确保 `plugins/ddw_contact_hub/manifest.yaml` 存在
2. 平台启动时 `core/main.py:load_plugins()` 会自动扫描并加载
3. **依赖插件**：`ddw-company-profile`（联系人的 `company_id` 引用 `crm_companies.id`）

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `default_tenant_id` | int | 1 | 默认租户 |
| `default_page_size` | int | 20 | 列表默认分页大小 |
| `statuses` | array | `[active, inactive, archived]` | 状态枚举 |
| `max_tags_per_contact` | int | 20 | 单个联系人最大标签数 |
| `max_groups_per_contact` | int | 10 | 单个联系人最大分组数 |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_contact_hub/tests/ -v --tb=short
```

测试覆盖：
- ✅ 创建（独立 / 关联企业）
- ✅ 列表（分页 / 按企业筛选 / 模糊搜索）
- ✅ 详情（存在 / 不存在）
- ✅ 更新（正常 / 不存在）
- ✅ 硬删除
- ✅ by-company 端点（主联系人优先）
- ✅ 统计概览

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户
- `core.database.models.TimestampMixin` —— 时间戳
- `core.database.tenant_filter.bypass_tenant_filter` —— 绕过租户过滤（仅限开发/admin）
- `sdk.plugin_base.PluginBase` —— 插件基类
- `ddw-company-profile` —— 插件依赖（外键 `crm_companies.id`）

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
