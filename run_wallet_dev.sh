#!/bin/bash
# DDW 预付费钱包插件开发（MiMo Code headless + AHE Loop）
# 2026-08-05 用户指令：开始开发，loop 自循环质量保障
export PATH="/opt/homebrew/bin:$PATH"
cd /Users/chenye/workspace/DDW底座平台/ddw-ai-hub
caffeinate -d -i -s -u &

PROMPT='按 docs/wallet-TASK_SPEC-v1.0.md 完整实现 DDW 预付费钱包插件 ddw_wallet。项目根 /Users/chenye/workspace/DDW底座平台/ddw-ai-hub，插件目录 plugins/ddw_wallet/。

严格执行以下规则：
1. 目录结构严格按 TASK_SPEC 第1章：__init__.py / plugin.py / router.py / models.py / schemas.py / manifest.yaml / config.py / services/(account.py,recharge.py,charge.py,refund.py,royalty.py,wechat_pay.py,alipay_client.py) / tests/ / README.md / LICENSE
2. AHE Loop 边写边自评：每写一个文件立即 py_compile + ruff check --select=E,W,F --fix；每写一个模块立即写对应 pytest 并跑通；全部通过才写下一个模块
3. 每完成一个模块 git commit 一次，commit message 含 [LLM: mimo-code]，git add 只允许 plugins/ddw_wallet/ 目录，禁止 add 任何其他文件（仓库有其他未提交改动，绝不能混入）
4. 代码约束：Python 3.8+ 兼容（ECS 部署目标，需要时 from __future__ import annotations）；所有行不超过 88 字符；金额全用整数分禁止浮点；密钥只从环境变量读取禁止硬编码；测试全部 mock 不发起真实网络请求
5. 依赖安装用清华镜像 pip install -i https://pypi.tuna.tsinghua.edu.cn/simple/ wechatpayv3；微信支付用 wechatpayv3 官方 SDK，支付宝用 python-alipay-sdk
6. 数据库表名必须带 dw_wallet_ 前缀；SQLAlchemy 2.0 风格
7. 完成后跑全量验证：pytest plugins/ddw_wallet/tests/ -q 全部通过 + ruff check plugins/ddw_wallet/ --select=E,W,F 0 errors，然后汇报：文件清单、测试数、验证结果
8. 禁止触碰 plugins/ddw_wallet/ 目录以外的任何文件'

~/.mimocode/bin/mimo run "$PROMPT" \
  --file docs/wallet-TASK_SPEC-v1.0.md \
  --dangerously-skip-permissions \
  --model mimo/mimo-v2.5-pro \
  --title "ddw-wallet-dev" 2>&1 | tee /tmp/wallet_dev.log

echo "MIMO_EXIT=$?" >> /tmp/wallet_dev.log
