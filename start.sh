#!/bin/bash
# deepDDW 服务端启动/停止脚本
# 用法: bash start.sh [start|stop|restart|status]
# 数据与日志: ~/deepddw/data/ ~/deepddw/logs/

DEEPDDW_HOME="$HOME/deepddw"
PYTHON="/opt/homebrew/bin/python3.12"
PORT=8500

start() {
  if pgrep -f "uvicorn core.main:app" > /dev/null; then
    echo "deepDDW 已在运行 (端口 $PORT)"
    return 0
  fi
  cd "$DEEPDDW_HOME"
  set -a; . ./.env; set +a
  # --timeout-keep-alive 75：默认 5 秒太短，浏览器连接池复用到已关闭的空闲连接
  # 会报 "Load failed"（间歇性）；拉长让空闲连接存活更久。
  nohup "$PYTHON" -m uvicorn core.main:app --host 0.0.0.0 --port "$PORT" --timeout-keep-alive 75 > logs/deepddw.log 2>&1 &
  echo $! > .deepddw.pid
  sleep 5
  if curl -s http://127.0.0.1:$PORT/health > /dev/null; then
    echo "deepDDW 已启动: http://127.0.0.1:$PORT/ (PID $(cat .deepddw.pid))"
  else
    echo "⚠️ 启动可能失败，请查看 logs/deepddw.log"
  fi
}

stop() {
  if pgrep -f "uvicorn core.main:app" > /dev/null; then
    pkill -f "uvicorn core.main:app"
    echo "deepDDW 已停止"
  else
    echo "deepDDW 未在运行"
  fi
}

status() {
  if pgrep -f "uvicorn core.main:app" > /dev/null; then
    echo "运行中 (PID $(pgrep -f 'uvicorn core.main:app' | head -1))"
    curl -s http://127.0.0.1:$PORT/health
    echo
  else
    echo "未运行"
  fi
}

case "${1:-status}" in
  start) start ;;
  stop) stop ;;
  restart) stop; sleep 2; start ;;
  status) status ;;
  *) echo "用法: $0 [start|stop|restart|status]"; exit 1 ;;
esac
