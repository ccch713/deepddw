# DDW 业务架构（BA）· 流程分层视图

> **版本**：v1.0 初稿 · 2026-08-14
> **方法论**：华为企业架构 4A 之业务架构（BA）——"先有流程，再有组织；流程是战略资产"
> **流程分层**：L1 价值流 → L2 流程组 → L3 流程（对应插件）→ L4 活动（API）→ L5 任务 → L6 动作
> **对应审计项**：阶段 1-3（三模型审计综合定案 20260813，BA 评分 5/10，缺业务流程图）

---

## 一、L1 价值流（3 条，即 LTC 地图三链）

| L1 编码 | 价值流 | 华为对标 | 起点 → 终点 | 核心指标 |
|---|---|---|---|---|
| V1 | 获客签约 | LTC 前段 | 线索 → 订单 | 线索转化率、商机金额、合同额 |
| V2 | 交付履约 | LTC 后段/FDE | 订单 → 回款 | 部署周期、回款率、对账差异 |
| V3 | 服务续费 | ITR | 工单 → 续费 | 响应时长、工单闭环率、续费率 |

**L1 规则**：任何业务动作必须归属一条价值流；跨流交接点（订单→部署、合同→续费）是数据一致性重点。

---

## 二、L2 流程组（每价值流 4-6 组）

### V1 获客签约（L2）

| L2 编码 | 流程组 | 覆盖 L3 流程 | 关键插件 |
|---|---|---|---|
| V1-G1 | 线索管理 | 线索采集、认领、分配、清洗 | ddw_lead_claim、ddw_partner_directory |
| V1-G2 | 商机管理 | 商机创建、阶段推进、预测 | ddw_opportunity |
| V1-G3 | 报价管理 | 报价生成、审批、修订 | ddw_quotation |
| V1-G4 | 合同管理 | 合同起草、电子签、归档 | ddw_contract_core、ddw_signature_adapter |
| V1-G5 | 订单管理 | 订单生成、确认、变更 | ddw_order |

### V2 交付履约（L2）

| L2 编码 | 流程组 | 覆盖 L3 流程 | 关键插件 |
|---|---|---|---|
| V2-G1 | 部署交付 | 实例创建、环境绑定、验收 | ddw_instance_binding |
| V2-G2 | 授权管理 | 授权生成、发放、回收 | ddw_license_core |
| V2-G3 | 收款管理 | 在线支付、线下收款、退款 | ddw_wallet、ddw_offline_pos |
| V2-G4 | 对账开票 | 对账、差异处理、开票 | ddw_reconciliation、ddw_invoice |
| V2-G5 | 应收管理 | 应收登记、账龄、催收 | ddw_receivable |

### V3 服务续费（L2）

| L2 编码 | 流程组 | 覆盖 L3 流程 | 关键插件 |
|---|---|---|---|
| V3-G1 | 工单服务 | 工单创建、派单、升级、关闭 | ddw_support_ticket |
| V3-G2 | 客服应答 | 在线会话、知识库检索、转人工 | ddw_online_cs、ddw_knowledge_hierarchy |
| V3-G3 | 跟进闭环 | 回访、跟进记录、满意度 | ddw_followup |
| V3-G4 | 续费管理 | 到期预警、续费报价、续费订单 | ddw_renewal |

---

## 三、L3 流程（插件级，选列 15 个核心）

| L3 流程 | 所属 | 关键活动（L4 API） | 输入 → 输出 |
|---|---|---|---|
| 线索认领 | V1-G1 | POST /ddw-lead-claim/leads/claim | Lead → Lead(claimed) |
| 商机推进 | V1-G2 | PATCH /ddw-opportunity/opportunities/{id}/stage | Opportunity → 阶段+1 |
| 报价生成 | V1-G3 | POST /ddw-quotation/quotations | 商机 → 报价单 |
| 合同签署 | V1-G4 | POST /ddw-signature-adapter/requests | 合同 → 签署请求 |
| 订单确认 | V1-G5 | POST /ddw-order/orders | 合同 → 订单 |
| 实例部署 | V2-G1 | POST /ddw-instance-binding/instances | 订单 → 实例 |
| 授权发放 | V2-G2 | POST /ddw-license-core/licenses | 订单/实例 → 授权码 |
| 收款入账 | V2-G3 | POST /ddw_wallet/recharge | 支付回调 → 余额入账 |
| 对账确认 | V2-G4 | POST /ddw-reconciliation/confirm | 账单 → 对账结果 |
| 开票 | V2-G4 | POST /ddw-invoice/invoices | 对账 → 发票 |
| 应收登记 | V2-G5 | POST /ddw-receivable/receivables | 订单 → 应收 |
| 工单闭环 | V3-G1 | PATCH /ddw-support-ticket/tickets/{id}/close | 工单 → 已关闭 |
| 客服检索 | V3-G2 | POST /ddw_online_cs/chat | 提问 → 知识库回答 |
| 跟进记录 | V3-G3 | POST /ddw_followup/records | 会话 → 跟进记录 |
| 续费下单 | V3-G4 | POST /ddw-renewal/renewals | 到期合同 → 续费单 |

---

## 四、角色与场景（8 角色 × 3 场景）

### 角色体系（core/constants/roles.py 单一来源）

| 角色 | 所属组织 | 主要 L2 流程组 |
|---|---|---|
| superadmin | 平台 | 全部 |
| admin | 租户 | 全部（租户内） |
| channel_partner | 经销商 | V1-G1 线索、V2 交付 |
| sales | 销售 | V1-G1~G5 |
| cs | 客服 | V3-G1~G3 |
| finance | 财务 | V2-G3~G5 |
| member | 员工 | V3-G2 客服 |
| student | 学员（问渠） | 学习场景（独立） |

### 核心场景（Demo 用）

1. **场景 A（经销商获客）**：channel_partner 报备线索 → sales 认领 → 商机 → 报价 → 合同 → 订单 → 进入交付
2. **场景 B（财务收款）**：finance 查看订单 → 确认微信/支付宝入账（wallet）→ 对账 → 开票 → 应收台账
3. **场景 C（客户服务）**：cs 接工单 → 知识库自动应答 → 跟进 → 续费提醒 → 续费订单

---

## 五、流程责任与治理

| 项 | 现状 | 目标（下轮审计前） |
|---|---|---|
| 流程主人（GPO） | 未定义 | V1 营销线 / V2 销售线 / V3 服务线各 1 名 |
| 流程文档 | 本文档 + LTC 地图 | 每条 L2 补 SOP（阶段 3-3 客户成功手册合并） |
| 流程指标 | 无 | V1 转化率 / V2 回款周期 / V3 续费率（阶段 3-1 仪表盘） |
| 变更管理 | 插件评审（四条铁律） | 流程级变更评审（阶段 2-2 分级落地） |

---

## 六、验收

| # | 验收项 | 状态 |
|---|---|---|
| 1 | PRD/BA_业务架构.md 存在（L1-L3 分层） | ✅ 本文档 |
| 2 | 3 L1 价值流 + 14 L2 流程组 + 15 核心 L3 | ✅ |
| 3 | 与 LTC 地图/登记册/角色体系一致 | ✅ 交叉引用 |

---

*产出：Hermes Agent · 2026-08-14 · 阶段 1-3 交付物 1/2*
