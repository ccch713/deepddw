# DDW 售后工单插件（ddw-support-ticket v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P4-5** —— 客户报修 / 咨询 / 投诉 / 需求建议等工单的全生命周期管理。

## 功能描述

- **自动生成工单号**：`TKT-YYYYMMDD-NNN`（NNN 为当日序号，从 001 开始）
- **工单分类**：`bug` / `feature` / `question` / `complaint` / `other`
- **优先级**：`low` / `normal` / `high` / `urgent`
- **状态机**：`open` → `in_progress` → `resolved` → `closed`（可从 `open`/`in_progress` 跳到 `closed`）
- **处理人指派**：`assigned_to` (用户 ID) + 状态机联动
- **解决记录**：`resolution` 文本字段记录处理结论
- **多维筛选**：按企业 / 实例 / 分类 / 优先级 / 状态 / 处理人筛选
- **多租户隔离**：基于 `tenant_id` 的数据隔离

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /tickets | 新建工单（自动生成 ticket_no） |
| GET | /tickets | 工单列表（分页 + 多维筛选） |
| GET | /tickets/stats | 统计概览 |
| GET | /tickets/{id} | 工单详情 |
| PUT | /tickets/{id} | 更新工单 |
| POST | /tickets/{id}/assign | 指派处理人（open → in_progress） |
| POST | /tickets/{id}/start | 开始处理（open → in_progress） |
| POST | /tickets/{id}/resolve | 解决工单（in_progress → resolved） |
| POST | /tickets/{id}/close | 关闭工单（resolved → closed） |

## 数据模型

`SupportTicket` 表（`crm_support_tickets`）核心字段：

- **主键**：`id` (BigInt)
- **工单号**：`ticket_no` (unique, TKT-YYYYMMDD-NNN)
- **租户**：`tenant_id` (来自 `TenantMixin`)
- **关联**：`company_id` (FK → crm_companies.id, ON DELETE CASCADE) / `instance_id` (FK → crm_instances.id, nullable)
- **基本信息**：`title` / `description` / `category` / `priority`
- **处理**：`assigned_to` (用户 ID) / `resolution` / `resolved_at`
- **状态**：`status` (open/in_progress/resolved/closed)
- **审计**：`created_at` / `updated_at` (来自 `TimestampMixin`)

## 安装方法

插件随 DDW AI Hub 平台一起发布，无需独立安装。

## 配置项

`manifest.yaml` 的 `config_schema` 段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| default_tenant_id | int | 1 | 默认租户 |
| default_page_size | int | 20 | 列表默认分页大小 |
| categories | array | [bug, feature, question, complaint, other] | 工单分类枚举 |
| priorities | array | [low, normal, high, urgent] | 优先级枚举 |
| statuses | array | [open, in_progress, resolved, closed] | 状态机枚举 |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_support_ticket/tests/ -v --tb=short
```

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户
- `core.database.models.TimestampMixin` —— 时间戳
- `core.database.tenant_filter.bypass_tenant_filter` —— 绕过租户过滤
- `sdk.plugin_base.PluginBase` —— 插件基类
- `plugins.ddw_company_profile` / `plugins.ddw_instance_binding` —— 软依赖

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
