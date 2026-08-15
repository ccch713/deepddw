# DDW Invoice Plugin (P5-2)

销售端发票管理插件。`crm_invoices` 主表 + 12 个 REST 端点 + 客户自助下载 + 管理员批量上传。

## 功能

- **开票申请**：记录开票请求，初始 `status=requested`
- **上传发票**：财务上传发票文件，`status: requested → issued`，自动设置 `issued_at=今天`
- **作废发票**：`status: issued → voided`，`void_reason` 追加到 `notes`
- **客户侧开票申请（MVP）**：`POST /invoices/request` 自动从企业主体读取抬头和税号
- **客户自助下载**：`GET /invoices/{id}/download` 仅 `issued` 状态可下载，递增 `download_count`
- **管理员批量上传**：`POST /invoices/batch-upload` 一次提交多条，逐条独立处理（成功/失败不阻断）
- **多维筛选**：按企业 / 订单 / 发票类型（专票/普票）/ 状态 / 开票日期区间
- **统计概览**：各状态计数 + 价税合计/税额汇总 + 按发票类型分组 + 下载维度（`download_total` / `total_downloaded_files`）
- **EventBus 集成**：申请/开票/作废/批量开票/下载 时通过 `core.events.bus.get_bus()` 发布事件，供其他插件订阅

## 数据模型

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BigInt PK | 主键 |
| company_id | BigInt FK | 关联 `crm_companies.id`（ON DELETE SET NULL） |
| order_id | BigInt FK | 关联 `crm_orders.id`（ON DELETE SET NULL） |
| invoice_no | String(50) | 发票号（开具后由人工填入） |
| invoice_type | String(20) | `special`（专票）/ `normal`（普票） |
| amount | Numeric(12,2) | 不含税金额 |
| tax_amount | Numeric(12,2) | 税额 |
| total_amount | Numeric(12,2) | 价税合计（必须 = amount + tax_amount） |
| invoice_title | String(200) | 发票抬头 |
| tax_id | String(20) | 税号 |
| invoice_url | String(500) | 发票文件 URL（开具后填） |
| issued_at | Date | 开票日期 |
| status | String(20) | `requested` / `issued` / `voided` |
| notes | Text | 备注（作废时追加作废原因） |
| created_by | BigInt | 创建人 ID |
| created_at / updated_at | DateTime | 时间戳（TimestampMixin） |
| tenant_id | BigInt | 租户 ID（TenantMixin） |
| **notified_at** | DateTime | 通知时间（Task 1） |
| **notification_method** | String(20) | 通知方式 `email` / `sms` / `none`（Task 1） |
| **download_count** | Integer | 下载次数（Task 1） |
| **last_downloaded_at** | DateTime | 最后下载时间（Task 1） |
| **last_downloaded_by** | BigInt | 最后下载人 ID（Task 1） |
| **invoice_code** | String(50) | 发票代码（电子发票 10-12 位） |
| **invoice_check_code** | String(50) | 校验码（电子发票后 6 位） |
| **file_type** | String(10) | `pdf` / `ofd` / `xml` |
| **file_size_bytes** | Integer | 文件大小（字节） |

## 状态机

```
requested ──upload──▶ issued ──void──▶ voided
   │
   └─update─▶ requested （仅 requested 状态可改）
```

| 操作 | 允许的源状态 | 目标状态 |
|------|------------|---------|
| `update` | `requested` | `requested`（内容修改） |
| `upload` | `requested` | `issued` |
| `void` | `issued` | `voided` |
| `download` | `issued` | `issued`（仅递增 `download_count`） |

## API 端点（12 个）

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/invoices` | 新建开票申请（status=requested，管理员版） |
| GET | `/invoices` | 列表（分页 + 多维筛选） |
| GET | `/invoices/stats` | 统计（必须在 `/{id}` 之前） |
| GET | `/invoices/{id}` | 详情 |
| PUT | `/invoices/{id}` | 更新（仅 requested 状态） |
| POST | `/invoices/{id}/upload` | 上传发票（requested → issued） |
| POST | `/invoices/{id}/void` | 作废（issued → voided） |
| POST | `/invoices/request` | **客户提交开票申请（自动从企业主体填充抬头/税号）** |
| GET | `/invoices/my` | **客户查自己的发票列表**（按 company_id 过滤） |
| GET | `/invoices/{id}/download` | **客户下载发票**（仅 issued，递增计数） |
| POST | `/invoices/batch-upload` | **管理员批量上传**（多条独立处理） |

## 路由前缀

`/api/v1/plugins/ddw-invoice`

## EventBus 事件

| 事件名 | 触发时机 | payload |
|--------|----------|---------|
| `invoice.requested` | `create` / `request_by_customer` | invoice_id / company_id / total_amount |
| `invoice.issued` | `upload` | invoice_id / invoice_no / invoice_url / issued_at |
| `invoice.batch_issued` | `batch_upload` 完成（含失败汇总） | total / succeeded / failed / invoice_ids |
| `invoice.voided` | `void` | invoice_id / void_reason |
| `invoice.downloaded` | `record_download` | invoice_id / download_count / downloaded_by |

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
cloud-llm/ddw-ai-hub/.venv/bin/python3 -m pytest plugins/ddw_invoice/tests/ -v --tb=short
```

共 20 个测试用例：

1. `test_create_invoice` — 新建开票申请
2. `test_list_invoices_paginated` — 列表分页
3. `test_list_invoices_filter_by_type` — 按类型筛选
4. `test_get_invoice_detail` — 详情
5. `test_update_invoice` — 更新（仅 requested 状态）
6. `test_upload_invoice` — 上传（requested → issued，issued_at=今天）
7. `test_void_invoice` — 作废（issued → voided）
8. `test_stats_overview` — 统计概览
9. `test_request_by_customer_auto_fills_title` — 客户提交（自动填充抬头）
10. `test_request_by_customer_company_not_found` — 客户提交（企业不存在）
11. `test_list_by_company_paginated` — 客户列表分页
12. `test_list_by_company_filter_status` — 客户列表按状态筛选
13. `test_record_download_increments_count` — 下载计数递增
14. `test_download_invoice_not_issued` — 未开具状态不可下载
15. `test_admin_upload_invoice_with_extended_fields` — 上传带发票代码/校验码
16. `test_batch_upload_mixed_results` — 批量上传混合成功/失败
17. `test_stats_includes_download_metrics` — 统计含下载维度
18. `test_download_returns_invoice_download_resp` — 下载响应字段完整性
19. `test_upload_publishes_event` — upload 触发 EventBus
20. `test_record_download_publishes_event` — download 触发 EventBus

## 前端页面

- `frontend/invoice-portal.html` — 客户发票自助下载页（DDW Ant Design OA 风格）
- `frontend/saas-admin.html` — 管理控制台（财务→发票管理，含批量上传模态框）

## 资源消耗

- CPU：轻量级（典型 <5% CPU，FastAPI 单请求处理）
- 内存：基础 ~30 MB（插件加载 + 路由注册），峰值 ~80 MB（批量上传 50 条）
- 数据库存储：~300 字节/发票，10k 张 ≈ 3 MB
- 网络：上传依赖外部发票文件存储 URL（OSS / S3 / NAS），不消耗插件自身带宽