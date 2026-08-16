#!/usr/bin/env bash
# check_visibility.sh — 追踪 deepDDW 的曝光与增长（star / fork / 全站提及）
# 用法: bash scripts/check_visibility.sh
# 前置: gh CLI 已登录（gh auth status）
# 基线（2026-08-17 记录）: 3 stars / 2 forks / 入选 awesome-deepseek-harness
set -euo pipefail

REPO="ccch713/deepddw"

echo "== 仓库指标 =="
gh api "repos/$REPO" --jq '"stars: \(.stargazers_count)  forks: \(.forks_count)  open_issues: \(.open_issues_count)  watchers: \(.subscribers_count)"'

echo
echo "== 全部 stargazer（新增 = 与上次输出对比） =="
gh api "repos/$REPO/stargazers" --paginate --jq '.[].login' | sort -u

echo
echo "== 全站提及（GitHub code search，需登录态） =="
gh search code "deepddw" --limit 10 --json repository,path --jq '.[] | "\(.repository.full_name)  \(.path)"' 2>/dev/null || echo "(code search 不可用，跳过)"

echo
echo "== awesome 列表内状态（应仍在 Memory & Knowledge 节） =="
curl -s --max-time 20 "https://raw.githubusercontent.com/0xsline/awesome-deepseek-harness/main/README.md" \
  | grep -n "ccch713/deepddw" || echo "(列表中未找到——可能被移除，需核实)"
