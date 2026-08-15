# DDW 实收管理插件（ddw-payment v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P1-4** —— 实收流水记录与状态查询。

## 功能描述

提供销售侧实收（Payment）的录入、查询、筛选、统计能力：

- **主表结构**：单表 `crm_offline_pos_records`（Payment）；不分子表
- **业务关联**：可选外键到 `crm_companies`（客户企业），`ON DELETE SET NULL`
- **自动单号**：服务端按 `PAY-YYYYMMDD-NNN` 规则生成当日递增单号（NNN 从 001 开始）
- **支付方式**：`bank` / `cheque` / `cash` / `wechat` / `alipay`
- **状态机**（由本插件维护 + 由 P1-5 reconciliation 写入）：
  - `pending` — 待核销（默认新建状态）
  - `matched` — 已完全核销（`matched_amount >= amount`）
  - `partial` — 部分核销（`0 < matched_amount < amount`）
  - `unmatched` — 不匹配（核销后剩余金额被标记）
- **多维筛选**：按企业 ID / 付款方 / 单号 / 支付方式 / 状态 / 日期筛选
- **统计概览**：各状态计数 + 总收款金额 + 已核销金额 + 未核销金额
- **未核销列表**：只返回 `pending` / `partial` 状态（供 P1-5 reconciliation 拉取）
- **多租户隔离**：主表继承 `TenantMixin`

> **注意**：本插件**不**实现核销逻辑。`matched_amount` 字段保留，由 P1-5 reconciliation 写入，
> 本插件只负责记录实收 + 状态查询。

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET  | `/health` | 健康检查 |
| POST | `/payments` | 新建实收 |
| GET  | `/payments` | 列表（分页 + 筛选） |
| GET  | `/payments/unmatched` | 未核销列表（status=pending/partial） |
| GET  | `/payments/stats` | 统计概览 |
| GET  | `/payments/{id}` | 详情 |
| PUT  | `/payments/{id}` | 更新实收（仅 pending 状态可改） |

## 数据模型

`Payment`（`crm_offline_pos_records` 表，继承 `Base + TenantMixin + TimestampMixin`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BigInt | 主键 |
| `tenant_id` | BigInt | 租户 ID（TenantMixin） |
| `company_id` | BigInt? | 关联客户企业（crm_companies.id，SET NULL） |
| `payment_no` | String(30) | 单号 `PAY-YYYYMMDD-NNN`，唯一 |
| `payer_name` | String(200) | 付款企业全名（必填） |
| `bank_reference` | String(100)? | 银行流水号 |
| `amount` | Numeric(12,2) | 收款金额（必填） |
| `payment_date` | Date | 收款日期（必填，建索引） |
| `payment_method` | String(30) | 支付方式：bank/cheque/cash/wechat/alipay |
| `bank_account` | String(50)? | 收款账户 |
| `notes` | Text? | 备注 |
| `status` | String(20) | 状态（pending/matched/partial/unmatched） |
| `matched_amount` | Numeric(12,2) | 已核销金额（由 P1-5 写入） |
| `created_by` | BigInt? | 创建人 ID |
| `created_at` | DateTime | 创建时间（TimestampMixin） |
| `updated_at` | DateTime | 更新时间（TimestampMixin） |

## 目录结构

```
ddw_offline_pos/
├── LICENSE
├── README.md
├── __init__.py
├── manifest.yaml
├── models.py
├── plugin.py
├── router.py
├── schemas.py
├── services.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    └── test_offline_pos.py
```

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python3 -m pytest plugins/ddw_offline_pos/tests/ -v
```

覆盖 11 个测试用例：创建、单号格式、单号唯一性、列表、列表按支付方式筛选、列表按状态筛选、
详情、更新（pending）、未核销列表、统计概览、payer_name 必填校验。
