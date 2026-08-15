# DDW 录音与语音输入插件（ddw-voice-capture v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P3-1** —— 录音文件元数据管理。

## 功能描述

- **录音元数据上传**：file_url + file_size + duration_seconds + source_type
- **来源分类**：local / phone / meeting / memo
- **关联业务对象**：user_id / company_id / contact_id / opportunity_id
- **状态机**：uploaded → transcribed → processed / failed
- **软删除**：DELETE 走 status=failed 标记（保留审计）
- **多租户隔离**

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | /health | 健康检查 |
| POST | /voice-records | 上传录音元数据 |
| GET | /voice-records | 列表（分页 + 多维筛选） |
| GET | /voice-records/{id} | 详情 |
| DELETE | /voice-records/{id} | 软删除（status=failed） |
| GET | /voice-records/stats | 统计 |

## 数据模型

`VoiceRecord` 表（`crm_voice_records`）核心字段：

- **主键**：`id` (BigInt)
- **租户**：`tenant_id`
- **上传人**：`user_id` / `created_by`
- **关联**：`company_id` / `contact_id` / `opportunity_id` (FK + ON DELETE SET NULL)
- **文件**：`file_url` (String(500), NOT NULL) / `file_size` (Int, NOT NULL) / `duration_seconds` (Int, NOT NULL)
- **来源**：`source_type` (local/phone/meeting/memo)
- **状态**：`status` (uploaded/transcribed/processed/failed)
- **备注**：`notes`

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_voice_capture/tests/ -v --tb=short
```

## 依赖

- `core.database.session.Base`
- `core.database.models.TenantMixin` / `TimestampMixin`
- `sdk.plugin_base.PluginBase`

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
