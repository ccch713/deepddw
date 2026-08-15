#!/bin/bash
# 问渠学生端工作台开发（MiMo Code headless + AHE Loop）
# 2026-08-05 用户指令：自动化连续开发
export PATH="/opt/homebrew/bin:$PATH"
cd /Users/chenye/workspace/DDW底座平台/ddw-ai-hub
caffeinate -d -i -s -u &

mkdir -p frontend/wenqu/assets

PROMPT='按 docs/wenqu-student-TASK_SPEC-v1.0.md 实现问渠学生端工作台前端。项目根 /Users/chenye/workspace/DDW底座平台/ddw-ai-hub，输出目录 frontend/wenqu/。

严格执行：
1. 交付物：frontend/wenqu/student.html（单文件，内嵌全部 CSS/JS，三段式布局）+ frontend/wenqu/login.html + frontend/wenqu/assets/favicon.png（用 /Users/chenye/Documents/Obsidian Vault/01_Projects/DDW 1/03_插件/K12学习SaaS/品牌/wenqu-logo-A.png 复制缩放为 64x64 PNG）+ frontend/wenqu/README.md
2. AHE Loop 边写边自评：写完 student.html 后立即验证：node --check 提取的 JS 语法、headless Chrome dump-dom 断言三段式容器存在
3. 视觉规范严格按 TASK_SPEC 第4章（朱砂#B03A2E/宣纸#F7F1E3/墨#3A3A3A/金#E8C46B）
4. 布局严格按 TASK_SPEC 第2章（左240px课程树/中对话流式+快捷指令/右360px三Tab成果区）
5. API 对接层按 TASK_SPEC 第3章（fetch 封装 + 402 充值窗 + 流式渲染 + 错误处理），全部 try/catch
6. 零构建零 npm 依赖，原生 ES2020；二维码用内嵌 qrcode 生成函数（不接受 CDN 依赖）
7. 完成后验证并汇报：node --check 结果、headless DOM 断言输出、文件清单
8. 禁止修改 plugins/ 下任何文件；只允许在 frontend/wenqu/ 目录写文件'

~/.mimocode/bin/mimo run "$PROMPT" \
  --file docs/wenqu-student-TASK_SPEC-v1.0.md \
  --dangerously-skip-permissions \
  --model mimo/mimo-v2.5-pro \
  --title "wenqu-student-dev" 2>&1 | tee /tmp/wenqu_student_dev.log

echo "MIMO_EXIT=$?" >> /tmp/wenqu_student_dev.log
