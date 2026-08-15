# DDW Sales Copilot Plugin (ddw-sales-copilot v1.0.0)

DDW AI Hub Sales CRM plugin group **P3-4** — AI assistant for sales reps.

## Features

Based on data from P0-1~P0-5 / P1 / P2 / P3-1~P3-3, this plugin provides 5 AI capabilities:

- **Opportunity Stage Suggestion** — Reads opportunity basics + last 5 sales notes; LLM recommends next stage
- **Customer Risk Alert** — Evaluates stale days / stage / visit frequency; outputs low/medium/high risk level
- **Action Suggestion** — Combines opportunity + notes + quotation context; LLM generates next-step action list
- **Daily Sales Report** — Aggregates daily "opportunity / contact / quotation / note" metrics; LLM writes structured report
- **Weekly Sales Report** — Aggregates weekly metrics; LLM writes structured report

All AI inference goes through platform `embedded_llm.engine.EmbeddedLLM`. **No new tables created.** No API keys hard-coded.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET  | `/health` | Health check |
| POST | `/copilot/stage-suggestion` | Stage suggestion (input: `opportunity_id`) |
| POST | `/copilot/risk-alert` | Risk alert (input: `opportunity_id` or `company_id`) |
| POST | `/copilot/action-suggestion` | Action suggestion (input: `opportunity_id`) |
| POST | `/copilot/daily-report` | Daily report (input: `user_id` + `date`) |
| POST | `/copilot/weekly-report` | Weekly report (input: `user_id` + `week_start`) |

## License

Apache License 2.0 — 武汉锐果互动信息技术有限公司 (Wuhan Ruiguo Interactive Information Technology Co., Ltd.)
