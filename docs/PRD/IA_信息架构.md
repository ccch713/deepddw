# DDW 信息架构（IA）· 5 层数据架构视图

> **版本**：v1.0 初稿 · 2026-08-14
> **方法论**：华为 5 层数据架构（L1 主题域 → L2 概念模型 → L3 逻辑模型 → L4 物理模型 → L5 属性）
> **对应审计项**：阶段 1-3（三模型审计综合定案 20260813，IA 是审计最弱项：无数据字典/无分层/无主人，3.3/10）
> **数据来源**：`data/ddw_main.db` 实测 125 表 + 各插件 models.py

---

## 一、L1 主题域（5 域）

| L1 域 | 编码 | 覆盖范围 | 数据主人 | 表数（约） |
|---|---|---|---|---|
| 客户域 | DOM-C | 企业/联系人/经销商/线索 | 营销线 | 15 |
| 交易域 | DOM-T | 商机/报价/合同/订单/授权/实例/发票/应收 | 销售线 | 25 |
| 资金域 | DOM-F | 钱包/充值/消费/退款/审计/对账 | 财务线 | 12 |
| 服务域 | DOM-S | 工单/客服/知识库/跟进/续费 | 平台组代管 | 30 |
| 平台域 | DOM-P | 租户/用户/角色/令牌/审计/插件市场 | 平台组 | 40 |

> 剩余表为业务垂直插件私有表（问渠 wenqu_*、口腔 dental_*、ESG、培训 training_*、招投标 bid_*、合规 cert_* 等），纳入对应业务域，后续迭代扩展。

---

## 二、L2 概念模型（核心实体关系）

```
客户域: 企业(1)─(N)联系人 ; 企业(1)─(N)经销商关系 ; 线索(N)─(1)经销商
交易域: 商机(1)─(N)报价(1)─(N)合同(1)─(N)订单 ; 订单(1)─(1)授权 ; 订单(1)─(N)应收 ; 对账(N)─(N)订单
资金域: 钱包账户(1)─(N)充值单 ; (1)─(N)消费记录 ; (1)─(N)退款 ; (1)─(N)审计日志
服务域: 工单(1)─(N)跟进 ; 客服会话(N)─(1)知识文档 ; 合同(1)─(N)续费单
平台域: 租户(1)─(N)用户 ; 用户(N)─(N)角色 ; 用户(1)─(N)令牌 ; 插件市场(N)─(N)租户
```

---

## 三、L3/L4 逻辑→物理模型（核心表映射，与登记册一致）

### 客户域（DOM-C）

| L3 逻辑实体 | L4 物理表 | 来源插件 | 关键字段（L5 示例） |
|---|---|---|---|
| 企业 | crm_companies | ddw_company_profile | id, name, credit_code, tenant_id |
| 联系人 | crm_contacts | ddw_contact_hub | id, company_id, name, phone |
| 经销商 | crm_partners | ddw_partner_directory | id, name, level, region |
| 线索 | crm_lead_claims | ddw_lead_claim | id, company_id, owner_id, status |

### 交易域（DOM-T）

| L3 逻辑实体 | L4 物理表 | 来源插件 | 关键字段 |
|---|---|---|---|
| 商机 | crm_opportunities | ddw_opportunity | id, amount_cents, probability, stage |
| 报价 | crm_quotations | ddw_quotation | id, opp_id, amount_cents, status |
| 合同 | crm_contracts | ddw_contract_core | id, quotation_id, contract_no, amount |
| 订单 | crm_orders | ddw_order | id, contract_id, order_no, amount |
| 授权 | crm_licenses | ddw_license_core | id, license_key, valid_to, status |
| 实例 | crm_instances | ddw_instance_binding | id, order_id, instance_id, env |
| 发票 | crm_invoices | ddw_invoice | id, order_id, invoice_no, amount |
| 应收 | crm_receivables | ddw_receivable | id, order_id, amount, aging |

### 资金域（DOM-F）

| L3 逻辑实体 | L4 物理表 | 来源插件 | 关键字段 |
|---|---|---|---|
| 钱包账户 | dw_wallet_accounts | ddw_wallet | user_id, recharge_balance, income_balance, skin_balance |
| 充值单 | dw_wallet_recharge_orders | ddw_wallet | ref_id, amount, channel, status |
| 消费记录 | dw_wallet_charge_records | ddw_wallet | txn_id, user_id, amount, biz_ref |
| 退款 | dw_wallet_refund_records | ddw_wallet | charge_txn_id, amount, status |
| 审计 | dw_wallet_audit_logs | ddw_wallet | user_id, action, amount, balance_after |
| 对账 | （对账在服务层，无独立表） | ddw_reconciliation | 读钱包+订单侧数据比对 |

### 服务域（DOM-S）

| L3 逻辑实体 | L4 物理表 | 来源插件 | 关键字段 |
|---|---|---|---|
| 工单 | crm_support_tickets | ddw_support_ticket | id, company_id, subject, status |
| 客服会话 | （运行时内存+记忆） | ddw_online_cs | session_id, user_id |
| 知识库 | kh_documents / kb_documents | ddw_knowledge_hierarchy / ddw_ent_knowledge | id, title, scope, tenant_id |
| 知识块 | kh_chunks / kb_document_chunks | 同上 | doc_id, content, embedding |
| 续费 | （服务层，表待建） | ddw_renewal | contract_id, renew_at, status |

### 平台域（DOM-P）

| L3 逻辑实体 | L4 物理表 | 来源插件/模块 | 关键字段 |
|---|---|---|---|
| 租户 | tenants | core | id, name, plan |
| 用户 | users | core | id, tenant_id, phone, role |
| 角色 | roles | core | id, code, name |
| 令牌 | api_keys / token_quotas | core / ddw_token_manager | user_id, quota, used |
| 插件市场 | plugin_market_items | core | plugin_id, category, price_cny |
| 论坛 | forum_threads / forum_replies | core | thread_id, author_id |

---

## 四、L5 属性规范（通用约定）

| 约定 | 规则 |
|---|---|
| 主键 | 自增 `id`（BigInteger） |
| 租户隔离 | 核心表必须含 `tenant_id`（TenantMixin） |
| 金额 | 统一 `_cents`（分）整数存储，禁浮点 |
| 时间 | UTC ISO8601 字符串（`created_at`/`updated_at`） |
| 状态 | 小写枚举字符串（pending/active/closed） |
| 软删 | `deleted_at` 可空（有审计诉求的表） |
| 幂等 | 资金/交易表必有业务唯一键（ref_id/txn_id/order_no） |

---

## 五、数据治理缺口清单（下轮审计前）

| # | 缺口 | 现状 | 目标 |
|---|---|---|---|
| 1 | 数据字典 | 本文档 + 登记册（第一批 20 对象） | 全 125 表字典化 |
| 2 | 数据主人 | 3 域已定（客户/交易/资金） | 服务域明确主人 |
| 3 | 数据质量闭环 | 无巡检 | 阶段 2-3 巡检脚本（重复客户/孤儿订单/金额一致性） |
| 4 | 统一数据服务层 | 插件间直接 import models | core/data_service（MiMo 建议） |
| 5 | 主数据唯一约束 | 部分表缺唯一索引 | 登记册§三落地 |

---

## 六、验收

| # | 验收项 | 状态 |
|---|---|---|
| 1 | PRD/IA_信息架构.md 存在（L1-L5 分层） | ✅ 本文档 |
| 2 | 5 主题域 + 核心实体映射 + 属性规范 | ✅ |
| 3 | 表名与 ddw_main.db 实测一致 | ✅ 125 表核对 |

---

*产出：Hermes Agent · 2026-08-14 · 阶段 1-3 交付物 2/2*
