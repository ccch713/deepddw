# DDW 插件分级规范（Tiering）

> **版本**：v1.0 · 2026-08-14
> **定位**：华为"先僵化后固化再优化"的治理工具——客户/渠道一眼看清核心、实验、废弃
> **对应审计项**：阶段 2-2（三模型审计综合定案 20260813："插件分级未落地"）
> **前置**：TASK_SPEC_安全修复+插件分级_20260811.md（本次将其正式化并生效）

---

## 一、分级标准

| 级别 | 编码 | 定义 | 准入标准 | 退出条件 |
|---|---|---|---|---|
| **核心** | tier-core | 平台底座 + 三链（获客/履约/服务）关键路径 | ① 属于三链或平台基础能力 ② 全量测试覆盖 ③ 生产验证 ≥1 客户 | 链路重构/替换后降级 |
| **实验** | tier-beta | 垂直业务/工具型，单客户场景 | ① 有明确业务场景 ② 测试通过 ③ 迭代中 | 客户验证成功后晋升核心 |
| **废弃** | tier-archive | 已终止/替换/僵尸 | ① 无引用 ② 已归档 _archived/ | 清理或重写 |

**铁律**：
- Demo/交付默认只讲核心插件；实验插件按客户场景选择性展示
- 核心插件变更必须过四条铁律（冒烟/契约/角色/边界）
- 废弃插件不参与全量测试（pytest.ini norecursedirs 已排除 _archived）

---

## 二、分级清单（当前 87 插件 + 归档）

### Tier 1 · 核心（29）

**平台底座（9）**：ddw_memory、ddw_memory_knowledge_bridge、ddw_llm_gateway_plugin、ddw_social_login、ddw_authz、ddw_token_manager_plugin、ddw_org、ddw_docs_portal、ddw_connector

**链 1 获客（6）**：ddw_lead_claim、ddw_opportunity、ddw_quotation、ddw_contract_core、ddw_signature_adapter、ddw_order

**链 2 履约（8）**：ddw_instance_binding、ddw_license_core、ddw_wallet、ddw_offline_pos、ddw_reconciliation、ddw_invoice、ddw_receivable、ddw_partner_directory

**链 3 服务（6）**：ddw_support_ticket、ddw_online_cs、ddw_followup、ddw_knowledge_hierarchy、ddw_ent_knowledge、ddw_renewal

### Tier 2 · 实验（58）

**问渠 K12**：ddw_wenqu_tutor（*注：唯一 C 端付费产品线，客户验证后直晋核心*）

**口腔**：ddw_clinic_cs、ddw_clinical_asr、ddw_dental_emr、ddw_dental_imaging、ddw_dental_sterilization、ddw_informed_consent、ddw_patient_crm、ddw_doctor_schedule、ddw_inventory、ddw_commission、ddw_member_vip

**ESG**：ddw_esg_assessment、ddw_esg_chatbot、ddw_esg_knowledge、ddw_esg_payment、ddw_esg_question_bank、ddw_esg_report

**制造业/质检**：ddw_spc_basic、ddw_capa_workflow、ddw_quality_assistant、ddw_quality_knowledge、ddw_regulatory_evidence、ddw_personnel_qual、ddw_position_designer、ddw_cost_knowledge、ddw_bid_writer

**销售/营销**：ddw_sales_copilot、ddw_sales_dashboard、ddw_sales_note、ddw_marketing、ddw_product_catalog、ddw_opportunity_ext（无）

**培训/知识**：ddw_training、ddw_doc_assistant、ddw_kpi、ddw_kpi_dashboard、ddw_finance_dashboard、ddw_metric_dict、ddw_report

**AI 能力**：ddw_transcript_ai、ddw_voice_capture、ddw_talk_a1_asr、ddw_searxng、ddw_wecom、ddw_weaver、ddw_website、ddw_website_analytics、ddw_theme、ddw_account_linker、ddw_ai_readiness、ddw_clarify、ddw_flow_designer、ddw_saas_billing、ddw_token_entitlement、ddw_employee_roster

### Tier 3 · 废弃（归档 _archived/）

ddw-email-assistant、ddw-llm-gateway、ddw-smart-cs、ddw-token-manager、customer-service、integration_tests_legacy、ddw_aggregated_pay（已迁入）

---

## 三、落地机制（生效路径）

| # | 机制 | 状态 |
|---|---|---|
| 1 | 本规范为分级唯一来源 | ✅ v1.0 |
| 2 | 插件市场 UI 显示分级标记（核心⭐/实验🟡/废弃⚪） | 🔴 待前端接入（plugin-market.html + /admin/plugins） |
| 3 | manifest.yaml 增加 `tier:` 字段（脚本校验一致性） | 🔴 待批量补写（scripts/apply_plugin_tier.py） |
| 4 | Demo 物料按核心插件组织（LTC 三链 = 核心清单） | ✅ 已对齐（docs/DDW_LTC_主流程地图.md） |
| 5 | 分级变化走评审（四条铁律） | ✅ 制度已定 |

---

## 四、验收

| # | 验收项 | 状态 |
|---|---|---|
| 1 | 分级规范文档生效 | ✅ 本文档 |
| 2 | 核心/实验/废弃三档清单齐全 | ✅ 29+58+7 |
| 3 | 与 LTC 地图/测试排除/归档目录一致 | ✅ 交叉核对 |

---

*产出：Hermes Agent · 2026-08-14 · 阶段 2-2 交付物*
