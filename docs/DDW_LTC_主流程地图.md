# DDW LTC 主流程地图（三链一图）

> **版本**：v1.0 · 2026-08-14
> **定位**：华为"端到端三大价值流"（IPD/LTC/ITR）的 DDW 落地视图——把 86 个插件从"零件仓库"变成"装配图纸"
> **用途**：Demo 前置（嘉必优/问渠）、渠道培训、插件规划对齐
> **对应审计项**：阶段 1-1（三模型审计综合定案 20260813）

---

## 一、总览：DDW 三大价值链

| 链 | 华为对标 | DDW 主线 | 一句话 | 起点 → 终点 |
|---|---|---|---|---|
| **链 1 · 获客签约** | LTC 前段 | **线索 → 回款意向** | "把客户谈进来" | 官网线索 → 合同订单 |
| **链 2 · 交付履约** | LTC 后段 + FDE | **订单 → 上线回款** | "把产品装进去把钱收回来" | 订单 → 发票/对账 |
| **链 3 · 服务续费** | ITR | **工单 → 续费** | "把客户服务好留住" | 工单/客服 → 续费 |

> 华为 LTC 完整链路 = 链 1 + 链 2（获客到回款）；链 3 是独立价值流（问题到解决），DDW 把续费（新线索入口）挂在链 3 末端形成闭环。

---

## 二、链 1 · 获客签约（线索 → 订单）

```
官网/渠道  →  线索认领  →  商机跟进  →  报价  →  合同/电子签  →  订单
ddw_website_analytics / ddw_partner_directory → ddw_lead_claim → ddw_opportunity
→ ddw_quotation → ddw_contract_core + ddw_signature_adapter → ddw_order
```

| 环节 | 插件 | 数据对象 | 关键 API |
|---|---|---|---|
| 线索来源 | ddw_website_analytics / ddw_partner_directory | 访问/经销商 | /api/v1/plugins/ddw-website-analytics/... |
| 线索认领 | ddw_lead_claim | Lead | /api/v1/plugins/ddw-lead-claim/leads |
| 商机 | ddw_opportunity | Opportunity | /api/v1/plugins/ddw-opportunity/opportunities |
| 报价 | ddw_quotation | Quotation | /api/v1/plugins/ddw-quotation/quotations |
| 合同 | ddw_contract_core | Contract | /api/v1/plugins/ddw-contract-core/contracts |
| 电子签 | ddw_signature_adapter | SignatureRequest | /api/v1/plugins/ddw-signature-adapter/requests |
| 订单 | ddw_order | Order | /api/v1/plugins/ddw-order/orders |

**Demo 剧本（嘉必优）**：经销商报备线索 → 认领 → 建商机（金额/概率）→ 生成报价单 → 合同起草 + 电子签 → 订单生成 → 进入链 2。

---

## 三、链 2 · 交付履约（订单 → 回款）

```
订单 → 实例绑定/部署 → 授权发放 → 收款 → 对账 → 开票 → 应收
ddw_order → ddw_instance_binding → ddw_license_core → ddw_wallet/ddw_offline_pos
→ ddw_reconciliation → ddw_invoice → ddw_receivable
```

| 环节 | 插件 | 数据对象 | 关键 API |
|---|---|---|---|
| 订单承接 | ddw_order | Order | /api/v1/plugins/ddw-order/orders |
| 部署绑定 | ddw_instance_binding | InstanceBinding | /api/v1/plugins/ddw-instance-binding/instances |
| 授权发放 | ddw_license_core | License | /api/v1/plugins/ddw-license-core/licenses |
| 收款 | ddw_wallet / ddw_offline_pos | WalletTxn / Payment | /api/v1/plugins/ddw_wallet/... |
| 对账 | ddw_reconciliation | Reconciliation | /api/v1/plugins/ddw-reconciliation/... |
| 开票 | ddw_invoice | Invoice | /api/v1/plugins/ddw-invoice/invoices |
| 应收 | ddw_receivable | Receivable | /api/v1/plugins/ddw-receivable/receivables |

**Demo 剧本（问渠/嘉必优）**：订单 → 实例绑定（客户现场部署登记）→ 授权码发放 → 微信/支付宝收款（wallet）→ 对账一致 → 开票 → 应收台账。

---

## 四、链 3 · 服务续费（工单 → 续费）

```
工单/客服 → 跟进 → 知识库 → 续费
ddw_support_ticket / ddw_online_cs → ddw_followup → ddw_knowledge_hierarchy
/ ddw_ent_knowledge → ddw_renewal
```

| 环节 | 插件 | 数据对象 | 关键 API |
|---|---|---|---|
| 工单 | ddw_support_ticket | Ticket | /api/v1/plugins/ddw-support-ticket/tickets |
| 在线客服 | ddw_online_cs | Session | /api/v1/plugins/ddw_online_cs/health |
| 跟进 | ddw_followup | Followup | /api/v1/plugins/ddw_followup/... |
| 知识库 | ddw_knowledge_hierarchy / ddw_ent_knowledge | KB | /api/v1/plugins/ddw-knowledge-hierarchy/... |
| 续费 | ddw_renewal | Renewal | /api/v1/plugins/ddw-renewal/renewals |

**Demo 剧本**：客户提工单 → 客服/知识库自动应答 → 跟进闭环 → 到期前续费提醒 → 续费订单回流链 1/2。

---

## 五、验收标准（对应审计 1-1）

| # | 验收项 | 状态 |
|---|---|---|
| 1 | `docs/DDW_LTC_主流程地图.md` 存在且三链完整 | ✅ 本文档 |
| 2 | 3 张价值链 HTML（docs/value-chains/） | ✅ value-chain-1/2/3.html |
| 3 | 3 个 smoke 脚本（scripts/smoke_value_chain_*.sh） | ✅ 对应文件 |
| 4 | 嘉必优/问渠 Demo 前 3 条剧本可讲 | ✅ 上文剧本段 |

## 六、执行命令

```bash
# 本地验证链路插件健康（需本地服务运行）
bash scripts/smoke_value_chain_1_hook.sh
bash scripts/smoke_value_chain_2_delivery.sh
bash scripts/smoke_value_chain_3_service.sh

# ECS 生产验证
ssh root@8.145.35.164 "cd /opt/ddw/ddw-ai-hub && bash scripts/smoke_value_chain_1_hook.sh"
```

---

*产出：Hermes Agent · 2026-08-14 · 阶段 1-1 交付物 1/3*
