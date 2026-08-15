#!/bin/bash
# DDW 密码生命周期补丁开发（mimocode 单 phase）
set -uo pipefail
export PATH="/opt/homebrew/bin:$PATH"

PROJECT_DIR="$HOME/workspace/DDW底座平台/ddw-ai-hub"
MIMO="$HOME/.mimocode/bin/mimo"
SPEC="$PROJECT_DIR/docs/TASK_SPEC_password_policy.md"
LOG="$PROJECT_DIR/dev-log/password_policy_dev.log"

mkdir -p "$PROJECT_DIR/dev-log"
caffeinate -d -i -s -u &
CAFFEINATE_PID=$!

cd "$PROJECT_DIR"
echo "[$(date '+%H:%M:%S')] PHASE 1 START" >> "$LOG"
$MIMO run "阅读 TASK_SPEC_password_policy.md（--file 已附加），完整实现密码生命周期补丁：1) 新建 core/auth/password_policy.py（validate_password_strength：>=8位+含字母数字+拒绝纯字母/纯数字/连续重复/常见弱密码表）；2) core/api/auth.py 新增 POST /change-password 端点（current_user 认证、旧密码校验、强度校验、新旧不同、IP 限流 5次/小时、更新 hash 与 password_changed_at）；3) 登录端点（login-password 与 login）响应加 password_expired/must_change 字段（password_changed_at 为空或超 90 天=必须改密）；4) register 用强度校验替代 min_length=8 并设置 password_changed_at；5) core/database/models.py 的 User 加 password_changed_at 字段；6) core/config.py 加 password_max_age_days 默认 90（环境变量 DDW_PASSWORD_MAX_AGE_DAYS 可覆盖）；7) 新建 frontend/change-password.html（原密码/新密码/确认，前端即时校验，成功后跳 admin.html）；8) login.html/welcome.html 登录响应 must_change=true 时跳转 change-password.html；9) saas-register.html 加密码强度提示文案；10) 追加 tests/test_password_policy.py 全部 9 条测试并跑通；11) 全量 pytest 确认无回归。铁律：不破坏 P0 已验证码/限流/防枚举/设备绑定；密码哈希沿用 hash_password；前端 CSS 变量风格。" --file "$SPEC" --dangerously-skip-permissions --model mimo/mimo-v2.5-pro --variant high 2>&1 | tee -a "$LOG" || true

cd "$PROJECT_DIR"
git add core/ frontend/ tests/ requirements.txt docs/ scripts/ 2>/dev/null || true
git commit -m "feat(password-policy): 自助改密+强度策略+定期更换 [LLM: mimo-code]" 2>/dev/null || true
echo "[$(date '+%H:%M:%S')] PHASE 1 DONE" >> "$LOG"
kill $CAFFEINATE_PID 2>/dev/null || true
echo "COMPLETED"
