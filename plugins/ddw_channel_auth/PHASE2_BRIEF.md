# Phase 2 Brief：补充 9 条测试用例 + 全量 pytest 通过

**目标**：在 plugins/ddw_channel_auth/tests/ 下补充 9 条核心 pytest 用例（test_*.py），覆盖 TASK_SPEC §六 列出的关键业务逻辑，并确保 pytest 10/10 全绿。

## 必须实现的 9 条用例（每条一条 test_function）

1. test_claim_state_machine_transitions_claimed_to_paid
   - 路径: tests/test_claims.py
   - 流程: 创建 claim → 上传合同 → 标记支付 → 断言 state="paid"
   - 验证 services.py 的 ClaimService.create_claim + mark_contract_uploaded + mark_paid

2. test_claim_first_to_upload_contract_wins
   - 路径: tests/test_claims.py
   - 流程: 同公司 2 个 claim（不同时刻），第二个上传合同不会被选中
   - 断言 is_first_to_upload_contract == False for the second

3. test_claim_first_to_pay_wins_in_release_window
   - 路径: tests/test_claims.py
   - 流程: release 一个 claim 后，新 claim 先付 = 得

4. test_swap_broadcast_marks_old_code_grace_then_revoked
   - 路径: tests/test_license_codes.py
   - 流程: 发新码 → swap → 断言旧码 swap_grace_until != None + revoke_status="grace_countdown"

5. test_payment_amount_mismatch_returns_422
   - 路径: tests/test_payments.py
   - 流程: PaymentAutoVerifyReq amount_cents != quote_amount_cents → assert 422

6. test_trial_starts_30_days_full_features
   - 路径: tests/test_trials.py
   - 流程: POST /trials/{plugin_id}/start → 断言 days_remaining=30

7. test_poc_report_generates_pdf_and_docx_locally
   - 路径: tests/test_trials.py
   - 流程: 调用 trial_poc.render_poc_pdf + render_poc_docx → 断言 bytes 长度 > 1000

8. test_one_level_distribution_redline_blocks_subagent_creation
   - 路径: tests/test_one_level_redline.py
   - 流程: 调用试图创建下级渠道的内部函数 → assert HTTPException 403 with 红线文案

9. test_difficult_customer_flagged_when_threshold_reached
   - 路径: tests/test_difficult_customers.py
   - 流程: 同 company_id 被 3 个 partner 在 >6 个月窗口报备 → 自动标记

## 测试共性要求

- 使用 conftest.py 已有的 db fixture + client fixture
- 用 FastAPI AsyncClient
- 编号只用 ASCII 1/2/3+ABC
- 中文断言消息（业务可读）
- assert 失败要写 clear 中文 message

## 不要做的事

- 不要改已通过的 conftest.py（除非必要）
- 不要修改 models.py / schemas.py（除非缺必要 schema）
- 不要 import 任何云端 LLM
- 不要新增依赖包

完成后运行：
```bash
cd /Users/chenye/workspace/DDW底座平台/ddw-ai-hub && \
source .venv/bin/activate 2>/dev/null || python3 -m pytest plugins/ddw_channel_auth/tests/ -v --tb=short 2>&1 | tail -50
```

最终输出 pytest "10 passed" 才算完成。如有失败,就修复代码直到通过。
