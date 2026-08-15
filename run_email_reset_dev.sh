#!/bin/bash
# DDW 邮箱绑定+邮件找回密码开发（mimocode 单 phase）
set -uo pipefail
export PATH="/opt/homebrew/bin:$PATH"

PROJECT_DIR="$HOME/workspace/DDW底座平台/ddw-ai-hub"
MIMO="$HOME/.mimocode/bin/mimo"
SPEC="$PROJECT_DIR/docs/TASK_SPEC_email_reset.md"
LOG="$PROJECT_DIR/dev-log/email_reset_dev.log"

mkdir -p "$PROJECT_DIR/dev-log"
caffeinate -d -i -s -u &
CAFFEINATE_PID=$!

cd "$PROJECT_DIR"
echo "[$(date '+%H:%M:%S')] PHASE 1 START" >> "$LOG"
$MIMO run "阅读 TASK_SPEC_email_reset.md（--file 已附加），完整实现邮箱绑定与邮件找回密码：1) 新建 core/email.py（SMTP 异步发送模块，环境变量 DDW_SMTP_HOST/PORT/USER/PASSWORD/SENDER，阿里云企业邮箱默认 smtp.qiye.aliyun.com:465，未配置时 production 报错/非 production 降级日志打印）；2) core/database/models.py User 加 email/email_verified 字段；3) core/api/auth.py 新增 POST /forgot-password、POST /reset-password、POST /verify-email 端点（图形验证码前置、邮箱验证码 6 位 TTL 300s Redis+内存双写、防枚举 sent:true、限流 60s/邮箱 + 10次/分 IP、强度校验复用 password_policy、重置后 password_changed_at=now+email_verified=True）；4) RegisterReq 加 email 必填 + 注册后发邮箱验证邮件；5) 新建 frontend/forgot-password.html（三步流程：邮箱+图形验证码→发码→验证码+新密码+确认，前端即时强度提示，成功跳 login.html）；6) frontend/login.html 加忘记密码链接；7) frontend/saas-register.html 加邮箱必填字段；8) scripts/migrate_login_security.py 加 email/email_verified 幂等迁移；9) 新建 tests/test_email_reset.py 全部 10 条测试并跑通；10) 全量 pytest 确认无回归（70+10）。铁律：不破坏既有验证码/限流/防枚举/设备绑定/密码生命周期；前端 CSS 变量风格；邮件 HTML 中文化署名武汉锐果互动信息技术有限公司。" --file "$SPEC" --dangerously-skip-permissions --model mimo/mimo-v2.5-pro --variant high 2>&1 | tee -a "$LOG" || true

cd "$PROJECT_DIR"
git add core/ frontend/ tests/ requirements.txt docs/ scripts/ 2>/dev/null || true
git commit -m "feat(email-reset): 邮箱绑定+邮件验证码找回密码 [LLM: mimo-code]" 2>/dev/null || true
echo "[$(date '+%H:%M:%S')] PHASE 1 DONE" >> "$LOG"
kill $CAFFEINATE_PID 2>/dev/null || true
echo "COMPLETED"
