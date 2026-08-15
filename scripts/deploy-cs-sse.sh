#!/bin/bash
# AI客服SSE流式优化 — ECS一键部署脚本
# 用法: bash deploy-cs-sse.sh
# 前提: SSH可连通ECS (ssh root@121.4.222.194)

set -e
ECS="root@121.4.222.194"
LOCAL="/Users/chenye/workspace/DDW底座平台/ddw-ai-hub"
REMOTE="/opt/ddw/ddw-ai-hub"

echo "=== 1. 同步后端文件 ==="
scp -o ConnectTimeout=10 \
  "$LOCAL/core/llm_gateway/minimax.py" \
  "$LOCAL/core/llm_gateway/deepseek.py" \
  "$LOCAL/plugins/ddw_online_cs/router.py" \
  "$ECS:$REMOTE/core/llm_gateway/"

scp -o ConnectTimeout=10 \
  "$LOCAL/plugins/ddw_online_cs/router.py" \
  "$ECS:$REMOTE/plugins/ddw_online_cs/"

echo "=== 2. 同步前端文件 ==="
scp -o ConnectTimeout=10 \
  "$LOCAL/frontend/company/assets/js/site-common.js" \
  "$ECS:$REMOTE/frontend/company/assets/js/"

echo "=== 3. 重启后端服务 ==="
ssh -o ConnectTimeout=10 "$ECS" "cd $REMOTE && systemctl restart ddw-ai-hub 2>/dev/null || docker restart ddw-ai-hub 2>/dev/null || echo '请手动重启服务'"

echo "=== 4. 验证 ==="
curl -s -o /dev/null -w "前端: %{http_code}\n" https://www.9cio.com/
curl -s -o /dev/null -w "客服API: %{http_code}\n" -X POST https://ddw.9cio.com/api/v1/plugins/ddw_online_cs/health
curl -s -o /dev/null -w "流式端点: %{http_code}\n" -X POST https://ddw.9cio.com/api/v1/plugins/ddw_online_cs/chat/stream \
  -H "Content-Type: application/json" -d '{"message":"测试","mode":"presales"}'

echo "=== 部署完成 ==="
