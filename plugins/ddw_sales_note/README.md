# DDW 拜访与沟通记录插件（ddw-sales-note v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P3-2** —— 拜访、电话、会议、邮件、微信沟通记录。

## 功能描述

- **记录类型**：visit / call / meeting / email / wechat
- **内容管理**：title + content（必填）
- **时间**：visit_date（拜访/沟通发生时间，可空表示其他类型）
- **关联业务对象**：user_id（记录人） / company_id / contact_id / opportunity_id
- **标签**：tags（JSON list）
- **附件**：attachments（JSON list，URL 列表）
- **按商机查询**：/notes/by-opportunity/{opportunity_id}
- **日期范围筛选**：visit_date 范围
- **最近 30 天统计**：`recent_30d` 字段（visit_date 在最近 30 天内的记录数）
- **硬删除**：DELETE 走物理删除（区别于其他插件的软删除）

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /notes | 新建拜访/沟通记录 |
| GET | /notes | 列表（分页 + 多维筛选） |
| GET | /notes/by-opportunity/{opportunity_id} | 某商机下所有记录 |
| GET | /notes/{id} | 详情 |
| PUT | /notes/{id} | 更新 |
| DELETE | /notes/{id} | **硬删除** |
| GET | /notes/stats | 统计（含 recent_30d） |

## 数据模型

`SalesNote` 表（`crm_sales_notes`）核心字段：

- **主键**：`id` (BigInt)
- **租户**：`tenant_id`
- **记录人**：`user_id`
- **关联**：`company_id` / `contact_id` / `opportunity_id` (FK + ON DELETE SET NULL)
- **类型**：`note_type` (visit/call/meeting/email/wechat)
- **内容**：`title` / `content` (Text, NOT NULL)
- **时间**：`visit_date` (DateTime, index)
- **扩展**：`tags` (JSON list) / `attachments` (JSON list)

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_sales_note/tests/ -v --tb=short
```

## 依赖

- `core.database.session.Base`
- `core.database.models.TenantMixin` / `TimestampMixin`
- `sdk.plugin_base.PluginBase`

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
