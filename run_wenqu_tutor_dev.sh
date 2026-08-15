#!/bin/bash
# 问渠学科包插件开发（MiMo Code headless + AHE Loop）
# 2026-08-05 用户指令：钱包完成后自动续开发
export PATH="/opt/homebrew/bin:$PATH"
cd /Users/chenye/workspace/DDW底座平台/ddw-ai-hub
caffeinate -d -i -s -u &

PROMPT='按 docs/wenqu-tutor-TASK_SPEC-v1.0.md 完整实现问渠学科包插件 ddw_wenqu_tutor。项目根 /Users/chenye/workspace/DDW底座平台/ddw-ai-hub，插件目录 plugins/ddw_wenqu_tutor/。

严格执行：
1. 目录结构严格按 TASK_SPEC 第1章（含 prompt/ 5 个文件，完整文本照抄第5.1节）
2. AHE Loop 边写边自评：每写一个文件立即 py_compile + ruff check --select=E,W,F --fix；每写一个模块立即写对应 pytest 并跑通；全部通过才写下一个模块
3. 每完成一个模块 git commit 一次，commit message 含 [LLM: mimo-code]，git add 只允许 plugins/ddw_wenqu_tutor/ 目录
4. 代码约束：Python 3.8+ 兼容（需要时 from __future__ import annotations）；所有行不超过 88 字符；金额全整数分禁止浮点；密钥只从环境变量读取；测试全部 mock（mock LLM + mock 钱包客户端），不发起真实网络请求
5. 钱包对接：services/session.py 中通过 HTTP 调用钱包 API（配置 DDW_WENQU_TUTOR_WALLET_BASE），测试中用 mock 替换，禁止真实调用
6. 数据库表名必须带 wenqu_ 前缀；SQLAlchemy 2.0 风格
7. 完成后跑全量验证：pytest plugins/ddw_wenqu_tutor/tests/ -q 全部通过 + ruff check plugins/ddw_wenqu_tutor/ --select=E,W,F 0 errors，汇报：文件清单、测试数、验证结果
8. 禁止触碰 plugins/ddw_wenqu_tutor/ 目录以外的任何文件，尤其禁止修改 plugins/ddw_wallet/'

~/.mimocode/bin/mimo run "$PROMPT" \
  --file docs/wenqu-tutor-TASK_SPEC-v1.0.md \
  --dangerously-skip-permissions \
  --model mimo/mimo-v2.5-pro \
  --title "wenqu-tutor-dev" 2>&1 | tee /tmp/wenqu_tutor_dev.log

echo "MIMO_EXIT=$?" >> /tmp/wenqu_tutor_dev.log
