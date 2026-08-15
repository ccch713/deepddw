# DDW 销售端 AI 副驾驶插件（ddw-sales-copilot v1.0.0）

DDW AI Hub 销售端 CRM 插件群 **P3-4** —— 销售员 AI 副驾驶。

## 功能描述

基于 P0-1~P0-5 / P1 / P2 / P3-1~P3-3 已落地的销售数据，为销售员提供 5 类 AI 辅助能力：

- **商机阶段建议** —— 读取商机基本信息 + 最近 5 条拜访记录，LLM 推荐下一步推进的阶段
- **客户风险提示** —— 评估「停滞天数 / 当前阶段 / 拜访频率」，LLM 给出 low/medium/high 风险等级及具体警示
- **行动建议** —— 综合商机 + 拜访 + 报价 3 类信息，LLM 生成可执行的下一步动作清单（联系客户/发送方案/安排演示等）
- **销售日报** —— 聚合指定销售当日的「商机 / 新增联系人 / 报价 / 拜访」指标，LLM 生成结构化日报
- **销售周报** —— 聚合指定销售本周的同类指标，LLM 生成结构化周报

所有 AI 推理走平台 `embedded_llm.engine.EmbeddedLLM`，不持有任何 API Key / 硬编码任何配置。
**本插件不创建任何新表**，所有数据走 SQLAlchemy 跨插件只读查询。

## API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| GET  | `/health` | 健康检查 |
| POST | `/copilot/stage-suggestion` | 商机阶段建议（输入 `opportunity_id`） |
| POST | `/copilot/risk-alert` | 客户风险提示（输入 `opportunity_id` 或 `company_id`） |
| POST | `/copilot/action-suggestion` | 行动建议（输入 `opportunity_id`） |
| POST | `/copilot/daily-report` | 销售日报（输入 `user_id` + `date`） |
| POST | `/copilot/weekly-report` | 销售周报（输入 `user_id` + `week_start`） |

## 请求 / 响应示例

### 1. 阶段建议

```http
POST /api/v1/plugins/ddw-sales-copilot/copilot/stage-suggestion
Content-Type: application/json

{
  "opportunity_id": 1,
  "tenant_id": 1
}
```

```json
{
  "opportunity_id": 1,
  "tenant_id": 1,
  "current_stage": "initial_contact",
  "current_stage_label": "初步接触",
  "suggested_stage": "demand_confirmation",
  "suggested_stage_label": "需求确认",
  "probability": 20,
  "reasoning": "[echo] kb='...' prompt='...'",
  "recent_notes_count": 3,
  "last_activity_at": "2026-08-03T10:00:00"
}
```

### 2. 风险提示

```http
POST /api/v1/plugins/ddw-sales-copilot/copilot/risk-alert
Content-Type: application/json

{ "opportunity_id": 1 }
```

```json
{
  "opportunity_id": 1,
  "tenant_id": 1,
  "risk_level": "high",
  "risk_score": 0.85,
  "risk_factors": ["stale_for_18_days", "no_recent_visits", "approaching_close_date"],
  "stale_days": 18,
  "last_activity_at": "2026-07-15T10:00:00",
  "alert": "[echo] ..."
}
```

### 3. 行动建议

```http
POST /api/v1/plugins/ddw-sales-copilot/copilot/action-suggestion
Content-Type: application/json

{ "opportunity_id": 1 }
```

```json
{
  "opportunity_id": 1,
  "tenant_id": 1,
  "priority": "high",
  "actions": [
    "立即电话联系客户确认需求",
    "发送详细方案和报价单",
    "安排现场演示"
  ],
  "reasoning": "[echo] ..."
}
```

### 4. 销售日报

```http
POST /api/v1/plugins/ddw-sales-copilot/copilot/daily-report
Content-Type: application/json

{ "user_id": 1, "date": "2026-08-03" }
```

```json
{
  "tenant_id": 1,
  "user_id": 1,
  "date": "2026-08-03",
  "metrics": {
    "opportunities_created": 2,
    "opportunities_updated": 5,
    "new_contacts": 1,
    "new_quotations": 1,
    "new_notes": 3
  },
  "highlights": ["成交 1 单 1000 元", "新增 2 个商机"],
  "report": "[echo] ..."
}
```

### 5. 销售周报

```http
POST /api/v1/plugins/ddw-sales-copilot/copilot/weekly-report
Content-Type: application/json

{ "user_id": 1, "week_start": "2026-07-27" }
```

```json
{
  "tenant_id": 1,
  "user_id": 1,
  "week_start": "2026-07-27",
  "week_end": "2026-08-02",
  "metrics": { "...": "..." },
  "highlights": ["..."],
  "report": "[echo] ..."
}
```

## 数据来源

- `crm_opportunities`（P0-3）—— 商机主表
- `crm_sales_notes`（P3-2）—— 拜访/沟通记录
- `crm_quotations`（P0-4）—— 报价单
- `crm_companies`（P0-1）—— 企业主体
- `crm_contacts`（P0-2）—— 联系人

## 风险判定规则（确定性逻辑 + LLM 综合判断）

| 维度 | low | medium | high |
|------|-----|--------|------|
| 停滞天数 | ≤ 3 | 4 ~ 13 | ≥ 14 |
| 阶段 | 已成交/合同待签 | 报价已发/商务谈判 | 初步接触/需求确认 |
| 拜访频率 | ≥ 1 / 周 | 1 / 两周 | 0 / 两周 |

LLM 收到的 prompt 中已包含上述确定性指标，最终的 `alert` / `reasoning` 字段直接透传 LLM 输出，便于后续切换到真实 LLM 时无需改 schema。

## 测试

```bash
cd /Users/chenye/workspace/ddw-ai-hub
python -m pytest plugins/ddw_sales_copilot/tests/ -v --tb=short
```

测试覆盖 7 个用例：

- ✅ 健康检查
- ✅ 阶段建议（正常路径 + LLM echo 验证）
- ✅ 风险提示 low（recently active）
- ✅ 风险提示 high（停滞 18 天 + 接近预期成交日）
- ✅ 行动建议
- ✅ 销售日报
- ✅ 销售周报

## 依赖

- `core.database.session.Base` —— ORM 根
- `core.database.models.TenantMixin` —— 多租户
- `core.database.tenant_filter.bypass_tenant_filter` —— 绕过租户过滤（开发/admin 模式）
- `embedded_llm.engine.EmbeddedLLM` —— 平台 LLM 网关
- `sdk.plugin_base.PluginBase` —— 插件基类
- 跨插件 ORM：`crm_opportunities` / `crm_sales_notes` / `crm_quotations` / `crm_companies` / `crm_contacts`

## License

Apache License 2.0 —— 武汉锐果互动信息技术有限公司
