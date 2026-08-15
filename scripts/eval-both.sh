#!/bin/bash
# DDW AI Hub v5.4 · 双 LLM Agent 自动评估脚本
# 当两个 Agent 写完代码后跑这个脚本来生成对比报告
# 用法：bash /Users/chenye/workspace/ddw-ai-hub/scripts/eval-both.sh

set -e

REPORT="/Users/chenye/Documents/Obsidian Vault/03_项目/统一框架/DDW_AI_Hub_v5.4/状态报告.md"
LOCAL_DIR="/Users/chenye/workspace/ddw-ai-hub/local-llm"
CLOUD_DIR="/Users/chenye/workspace/ddw-ai-hub/cloud-llm"

echo "===================================="
echo "DDW AI Hub · 双 LLM Agent 评估"
echo "===================================="
echo ""

# 评估 local-llm
echo "🔴 评估 local-llm (Ollama deepseek-coder-v2)..."
cd "$LOCAL_DIR"
LOCAL_PY=$(find ddw-ai-hub -name "*.py" 2>/dev/null | wc -l | xargs)
LOCAL_LOC=$(find ddw-ai-hub -name "*.py" 2>/dev/null | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}')

# py_compile
LOCAL_PASS=0
LOCAL_TOTAL=0
for f in $(find ddw-ai-hub -name "*.py" 2>/dev/null); do
    LOCAL_TOTAL=$((LOCAL_TOTAL + 1))
    if python3 -m py_compile "$f" 2>/dev/null; then
        LOCAL_PASS=$((LOCAL_PASS + 1))
    fi
done
LOCAL_RATE=$(echo "scale=1; $LOCAL_PASS * 100 / $LOCAL_TOTAL" | bc 2>/dev/null || echo "0")

# pytest
LOCAL_PYTEST=$(python3 -m pytest tests/ -q 2>&1 | grep -E "passed|failed" | tail -1 || echo "未跑通")

# import 测试
LOCAL_IMPORT=$(python3 -c "import sys; sys.path.insert(0, 'ddw-ai-hub'); import core.main" 2>&1 && echo "OK" || echo "FAIL")

# AHE Loop 状态
LOCAL_AHE=$(python3 .ahe-loop/ahe-loop.py status 2>&1 | head -5)

# 评估 cloud-llm
echo ""
echo "🔵 评估 cloud-llm (DeepSeek V4 Pro)..."
cd "$CLOUD_DIR"
CLOUD_PY=$(find ddw-ai-hub -name "*.py" 2>/dev/null | wc -l | xargs)
CLOUD_LOC=$(find ddw-ai-hub -name "*.py" 2>/dev/null | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}')

CLOUD_PASS=0
CLOUD_TOTAL=0
for f in $(find ddw-ai-hub -name "*.py" 2>/dev/null); do
    CLOUD_TOTAL=$((CLOUD_TOTAL + 1))
    if python3 -m py_compile "$f" 2>/dev/null; then
        CLOUD_PASS=$((CLOUD_PASS + 1))
    fi
done
CLOUD_RATE=$(echo "scale=1; $CLOUD_PASS * 100 / $CLOUD_TOTAL" | bc 2>/dev/null || echo "0")

CLOUD_PYTEST=$(python3 -m pytest tests/ -q 2>&1 | grep -E "passed|failed" | tail -1 || echo "未跑通")
CLOUD_IMPORT=$(python3 -c "import sys; sys.path.insert(0, 'ddw-ai-hub'); import core.main" 2>&1 && echo "OK" || echo "FAIL")
CLOUD_AHE=$(python3 .ahe-loop/ahe-loop.py status 2>&1 | head -5)

# 横向 diff（如果两个仓都产出文件）
echo ""
echo "🔀 横向 diff（同名文件）..."
DIFFS=""
for f in $(cd "$LOCAL_DIR" && find ddw-ai-hub -name "*.py" 2>/dev/null | sort); do
    if [ -f "$CLOUD_DIR/$f" ]; then
        DIFF_LINES=$(diff "$LOCAL_DIR/$f" "$CLOUD_DIR/$f" 2>/dev/null | wc -l | xargs)
        DIFFS="$DIFFS
  $f: 差异 $DIFF_LINES 行"
    fi
done

# 写报告
cat > "$REPORT" << EOF
# DDW AI Hub v5.4 · 开发状态报告

> **生成时间**：$(date '+%Y-%m-%d %H:%M:%S')
> **报告类型**：两 LLM Agent 横向对比

---

## 📊 总体进度

| 指标 | 🔴 local-llm (Ollama ds-coder-v2:16B) | 🔵 cloud-llm (DeepSeek V4 Pro) | 胜者 |
|---|---|---|---|
| 总 .py 文件数 | $LOCAL_PY | $CLOUD_PY | $([ $CLOUD_PY -gt $LOCAL_PY ] && echo "🔵" || echo "🔴") |
| 总 LOC | $LOCAL_LOC | $CLOUD_LOC | $([ $CLOUD_LOC -gt $LOCAL_LOC ] && echo "🔵" || echo "🔴") |
| py_compile 通过率 | $LOCAL_PASS/$LOCAL_TOTAL ($LOCAL_RATE%) | $CLOUD_PASS/$CLOUD_TOTAL ($CLOUD_RATE%) | $([ "$CLOUD_RATE" \> "$LOCAL_RATE" ] && echo "🔵" || echo "🔴") |
| pytest 通过数 | $LOCAL_PYTEST | $CLOUD_PYTEST | - |
| \`import core.main\` 成功 | $LOCAL_IMPORT | $CLOUD_IMPORT | - |

---

## 🔴 local-llm 详情

- **文件数**: $LOCAL_PY
- **LOC**: $LOCAL_LOC
- **py_compile**: $LOCAL_PASS / $LOCAL_TOTAL ($LOCAL_RATE%)
- **pytest**: $LOCAL_PYTEST
- **import 测试**: $LOCAL_IMPORT
- **AHE Loop 状态**:
\`\`\`
$LOCAL_AHE
\`\`\`

## 🔵 cloud-llm 详情

- **文件数**: $CLOUD_PY
- **LOC**: $CLOUD_LOC
- **py_compile**: $CLOUD_PASS / $CLOUD_TOTAL ($CLOUD_RATE%)
- **pytest**: $CLOUD_PYTEST
- **import 测试**: $CLOUD_IMPORT
- **AHE Loop 状态**:
\`\`\`
$CLOUD_AHE
\`\`\`

---

## 🔀 横向 diff（同名文件）

$DIFFS

---

## 🎯 你需要做的

1. 看上面表格判断哪个 LLM 更好
2. 决定保留哪个版本
3. 启动 Phase 2

EOF

echo ""
echo "===================================="
echo "✅ 报告已生成: $REPORT"
echo "===================================="
