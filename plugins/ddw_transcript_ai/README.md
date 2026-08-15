# DDW 转写与结构化插件（ddw-transcript-ai）

> DDW AI Hub — 销售端 CRM P3-3 插件

## 能力

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/plugins/ddw-transcript-ai/health` | GET | 健康检查 |
| `/api/v1/plugins/ddw-transcript-ai/transcript/transcribe` | POST | 录音转写（模拟 ASR） |
| `/api/v1/plugins/ddw-transcript-ai/transcript/summarize` | POST | 文本摘要 |
| `/api/v1/plugins/ddw-transcript-ai/transcript/extract-todos` | POST | 待办事项提取 |
| `/api/v1/plugins/ddw-transcript-ai/transcript/extract-entities` | POST | 关键实体抽取（公司/人名/金额/日期） |

## 架构

- **聚合 AI 能力插件**：无 ORM 表、无持久化
- LLM 调用走 `embedded_llm.engine.EmbeddedLLM`（默认 echo backend）
- 真实生产环境只需替换 LLM backend，业务层无改动
- 所有解析方法对 echo backend / 真实 LLM 都能产出合理结果

## 运行测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python3 -m pytest plugins/ddw_transcript_ai/tests/ -v
```

## 跨插件回归

```bash
python3 -m pytest plugins/ddw_company_profile/tests/ plugins/ddw_contact_hub/tests/ \
    plugins/ddw_opportunity/tests/ plugins/ddw_quotation/tests/ \
    plugins/ddw_sales_dashboard/tests/ plugins/ddw_contract_core/tests/ \
    plugins/ddw_order/tests/ plugins/ddw_receivable/tests/ \
    plugins/ddw_offline_pos/tests/ plugins/ddw_reconciliation/tests/ \
    plugins/ddw_finance_dashboard/tests/ plugins/ddw_partner_directory/tests/ \
    plugins/ddw_lead_claim/tests/ plugins/ddw_voice_capture/tests/ \
    plugins/ddw_sales_note/tests/ plugins/ddw_transcript_ai/tests/ -q
```
