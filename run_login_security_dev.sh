#!/bin/bash
# DDW 登录安全 P0 开发（mimocode 链式 3 phase + loop 自循环质量保证）
set -uo pipefail
export PATH="/opt/homebrew/bin:$PATH"

PROJECT_DIR="$HOME/workspace/DDW底座平台/ddw-ai-hub"
MIMO="$HOME/.mimocode/bin/mimo"
SPEC="$PROJECT_DIR/docs/TASK_SPEC_login_security.md"
LOG="$PROJECT_DIR/dev-log/login_security_dev.log"

mkdir -p "$PROJECT_DIR/dev-log"
caffeinate -d -i -s -u &
CAFFEINATE_PID=$!

# 确保开发产物不入库
cd "$PROJECT_DIR"
grep -q "^\.mimocode/" .gitignore 2>/dev/null || echo -e "\n.mimocode/\ndev-log/\n*.log" >> .gitignore
git add .gitignore && git commit -m "chore: gitignore dev artifacts" 2>/dev/null || true

run_phase() {
    local NUM="$1" NAME="$2" PROMPT="$3"
    echo "[$(date '+%H:%M:%S')] PHASE $NUM $NAME START" >> "$LOG"
    cd "$PROJECT_DIR"
    if [ "$NUM" = "1" ]; then
        $MIMO run "$PROMPT" --file "$SPEC" --dangerously-skip-permissions \
            --model mimo/mimo-v2.5-pro --variant high 2>&1 | tee -a "$LOG" || true
    else
        $MIMO run "$PROMPT" --continue --dangerously-skip-permissions \
            --model mimo/mimo-v2.5-pro --variant high 2>&1 | tee -a "$LOG" || true
    fi
    cd "$PROJECT_DIR"
    git add core/ frontend/ tests/ requirements.txt docs/ scripts/ 2>/dev/null || true
    git commit -m "feat(login-security): phase-$NUM $NAME [LLM: mimo-code]" 2>/dev/null || true
    echo "[$(date '+%H:%M:%S')] PHASE $NUM $NAME DONE" >> "$LOG"
    sleep 10
}

run_phase 1 "后端核心" "阅读 TASK_SPEC_login_security.md（--file 已附加），按第 4-8 节实现后端：新建 core/auth/captcha.py；改造 core/api/auth.py（GET /auth/captcha 端点、四层限流、防枚举统一 401 加虚拟 bcrypt、register 改手机号+密码+验证码、send-code 前置验证码、login_audit 写入、账号级设备绑定接入）；core/database/models.py 新增 LoginAudit 表和 User.device_required/device_allowlist 字段；core/auth/device_binding.py 新增 verify_user_device（device_required=False 放行，allowlist 优先，回退全局白名单）；requirements.txt 加 captcha 和 Pillow。然后按第 10 节编写 tests/test_login_security.py 全部 15 条测试并运行通过。铁律：不删除现有功能，不改 tenant_filter/JWT/bcrypt 格式，Redis 不可用降级内存。"

run_phase 2 "前端改造" "继续：按 TASK_SPEC 第 9 节改造前端。新建 frontend/js/fingerprint.js（采集 screen_resolution/canvas_hash/user_agent/timezone 组合 sha256，注入 window.DDW_FINGERPRINT）。改造 frontend/login.html：删除旧端点调用（/auth/sms/request、/auth/sms/verify、/auth/pin/login），改为手机号+密码+图形验证码单表单调 /api/v1/auth/login-password，验证码组件（图片+换一张+刷新+输入 maxlength=4），登录请求携带 device_fingerprint，429 显示 Retry-After 倒计时，记住账号 checkbox，删除 Dev Code toast。改造 frontend/welcome.html：删除万能码 8888 alert 和 dev_code console，登录表单加验证码组件。改造 frontend/saas-register.html：删除开发环境万能码 8888 文案和 dev_code 提示，注册表单加验证码组件。保持 CSS 变量风格。完成后 grep -rn '8888|万能码|dev_code' frontend/ 必须 0 命中。"

run_phase 3 "质量审计" "继续：独立质量审计（loop 自循环）。1) cd 项目根运行 python3 -m pytest tests/ -v 全量并修复所有失败（含存量回归）。2) 检查 auth.py 每个登录/注册/send-code 端点都有 captcha 校验和 429 处理。3) 检查 device_required 用户在任意部署 mode 下都强制设备验证（不得跳过 standalone）。4) 检查前端三页调用新端点且携带 device_fingerprint。5) 修复问题后再跑全量 pytest 确认全绿，最后输出审计结论清单（通过项+修复项）。"

kill $CAFFEINATE_PID 2>/dev/null || true
echo "[$(date '+%H:%M:%S')] ALL PHASES DONE" >> "$LOG"
echo "COMPLETED"
