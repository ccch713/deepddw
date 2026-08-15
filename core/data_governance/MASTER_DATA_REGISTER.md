# DDW 主数据登记册（MASTER DATA REGISTER）

> **版本**：v1.0 · 2026-08-14
> **定位**：华为"数据是流程中流淌的血液"的落地第一步——数据字典雏形 + 数据主人制
> **对应审计项**：阶段 1-2（三模型审计综合定案 20260813，IA 信息架构最弱项 3.3/10）
> **数据来源**：`data/ddw_main.db` 实表 + 各插件 models.py 定义（125 表，本册登记第一批 20 核心对象）

---

## 一、数据主人（3 域）

| 数据域 | 数据主人 | 覆盖对象 | 职责 |
|---|---|---|---|
| **客户域** | 渠道/客户管理（营销线） | 企业/联系人/经销商/线索 | 客户主数据唯一性、分级、归属 |
| **订单域** | 交易履约（销售线） | 商机/报价/合同/订单/授权/实例/发票/应收/签章 | 交易链路一致性、金额准确 |
| **钱包域** | 资金中台（财务线） | 钱包账户/充值/消费/退款/审计 | 资金安全、账实相符、审计合规 |

> 服务域（工单/知识库）暂由平台组代管，下轮审计前明确主人。

---

## 二、主数据登记（第一批 20 对象）

### 客户域（主人：营销线）

| # | 对象 | 表名 | 来源插件 | 说明 | 质量要点 |
|---|---|---|---|---|---|
| 1 | 企业 | crm_companies | ddw_company_profile | 客户企业主档 | 唯一性（统一社会信用代码/名称） |
| 2 | 联系人 | crm_contacts | ddw_contact_hub | 企业联系人 | 归属企业、电话格式 |
| 3 | 经销商 | crm_partners | ddw_partner_directory | 渠道伙伴档案 | 等级、区域、报备关系 |
| 4 | 线索 | crm_lead_claims | ddw_lead_claim | 销售线索 | 认领状态、归属、防重复认领 |

### 订单域（主人：销售线）

| # | 对象 | 表名 | 来源插件 | 说明 | 质量要点 |
|---|---|---|---|---|---|
| 5 | 商机 | crm_opportunities | ddw_opportunity | 销售机会 | 金额/概率/阶段 |
| 6 | 报价 | crm_quotations | ddw_quotation | 报价单（+明细表） | 报价与合同金额一致 |
| 7 | 合同 | crm_contracts | ddw_contract_core | 商务合同 | 合同号唯一、关联报价 |
| 8 | 订单 | crm_orders | ddw_order | 订单主档 | 订单号唯一、关联合同 |
| 9 | 授权 | crm_licenses | ddw_license_core | 产品授权/许可证 | 授权码唯一、有效期 |
| 10 | 实例绑定 | crm_instances | ddw_instance_binding | 客户部署实例 | 实例与客户/授权关联 |
| 11 | 发票 | crm_invoices | ddw_invoice | 发票台账 | 金额与回款匹配 |
| 12 | 应收 | crm_receivables | ddw_receivable | 应收账款 | 账龄、回款状态 |
| 13 | 电子签 | crm_signature_requests | ddw_signature_adapter | 签署请求 | 签署状态流转 |

### 钱包域（主人：财务线）

| # | 对象 | 表名 | 来源插件 | 说明 | 质量要点 |
|---|---|---|---|---|---|
| 14 | 钱包账户 | dw_wallet_accounts | ddw_wallet | 三钱包余额（充值/收入/皮肤） | 余额不变量：入账=出账+余额 |
| 15 | 充值单 | dw_wallet_recharge_orders | ddw_wallet | 充值订单 | 幂等（ref_id 唯一） |
| 16 | 消费记录 | dw_wallet_charge_records | ddw_wallet | 扣费流水 | 金额一致、关联业务单 |
| 17 | 退款记录 | dw_wallet_refund_records | ddw_wallet | 退款流水 | 退款≤原支付 |
| 18 | 资金审计 | dw_wallet_audit_logs | ddw_wallet | 余额变更审计 | 全量留痕、不可篡改 |

### 服务域（代管：平台组）

| # | 对象 | 表名 | 来源插件 | 说明 | 质量要点 |
|---|---|---|---|---|---|
| 19 | 工单 | crm_support_tickets | ddw_support_ticket | 客户服务工单 | 状态机闭环 |
| 20 | 知识文档 | kh_documents / kb_documents | ddw_knowledge_hierarchy / ddw_ent_knowledge | 企业知识库文档 | 版本、权限、来源可溯 |

---

## 三、数据质量闭环（下轮审计前落地项）

1. **重复客户巡检**：`SELECT name, COUNT(*) FROM crm_companies GROUP BY name HAVING COUNT(*)>1`（阶段 2-3 脚本化）
2. **孤儿订单巡检**：crm_orders 无关联合同 / crm_receivables 无关联订单
3. **金额一致性**：dw_wallet_accounts 余额 = Σcharge - Σrefund（按租户）
4. **唯一索引补强**：crm_companies(name)、crm_orders(order_no)、crm_licenses(license_key) 建唯一约束

## 四、验收

| # | 验收项 | 状态 |
|---|---|---|
| 1 | core/data_governance/MASTER_DATA_REGISTER.md 存在 | ✅ 本文档 |
| 2 | 20 对象 + 3 数据主人 | ✅ 见上 |
| 3 | 表名与实库一致（ddw_main.db 实测） | ✅ 125 表实测核对 |

---

*产出：Hermes Agent · 2026-08-14 · 阶段 1-2 交付物*
