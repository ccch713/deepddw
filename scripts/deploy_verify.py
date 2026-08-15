#!/usr/bin/env python3
"""DDW 一键部署端到端验证脚本 — 嘉必优现场演示前最后检查。

用法（ECS 上）:
    python3 /opt/ddw/ddw-ai-hub/scripts/deploy_verify.py

检查项:
  1. ddw-core 服务状态
  2. 插件加载数量 + 关键插件健康
  3. 质量插件群功能（SPC / 8D / CAPA）
  4. 在线客服 chat（kb+llm 双通道）
  5. 平台 LLM 网关 provider 状态
  6. 官网页面 HTTP 状态
  7. HRIS 适配器注册
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from typing import Any, Dict, List, Tuple

BASE = "/opt/ddw/ddw-ai-hub"
BASE_URL = "http://127.0.0.1:8500"
PASS, FAIL, WARN = "✅", "❌", "⚠️"

results: List[Tuple[str, str, str, str]] = []  # (category, check, status, detail)


def record(category: str, check: str, status: str, detail: str = "") -> None:
    results.append((category, check, status, detail))
    print(f"  {status} [{category}] {check}" + (f" — {detail}" if detail else ""))


def curl_json(method: str, path: str, body: Dict[str, Any] | None = None) -> Dict[str, Any] | None:
    cmd = ["curl", "-s", "-m", "20", "-X", method, f"{BASE_URL}{path}"]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "-d", json.dumps(body, ensure_ascii=False)]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
        return json.loads(out) if out.strip() else None
    except Exception:
        return None


def main() -> int:
    print("=" * 60)
    print("DDW 一键部署端到端验证 — 嘉必优现场前检查")
    print("=" * 60)

    # 1. 服务状态
    print("\n[1] 服务状态")
    r = subprocess.run(["systemctl", "is-active", "ddw-core"], capture_output=True, text=True, timeout=10)
    record("服务", "ddw-core", PASS if r.stdout.strip() == "active" else FAIL, r.stdout.strip())

    # 2. 插件加载
    print("\n[2] 插件加载")
    log = subprocess.run(
        ["journalctl", "-u", "ddw-core", "--no-pager", "-n", "200"],
        capture_output=True, text=True, timeout=15
    ).stdout
    loaded_match = [l for l in log.splitlines() if "plugins loaded" in l]
    if loaded_match:
        n = loaded_match[-1].split("plugins loaded")[0].split()[-1]
        record("插件", f"加载数量 {n}", PASS if int(n) >= 40 else WARN)
    else:
        record("插件", "加载数量", FAIL, "日志无 plugins loaded")

    # 关键插件健康
    for name, path in [
        ("在线客服", "/api/v1/plugins/ddw_online_cs/health"),
        ("SPC", "/api/v1/plugins/ddw-spc-basic/health"),
        ("质量助手", "/api/v1/plugins/ddw-quality-assistant/health"),
        ("CAPA", "/api/v1/plugins/ddw-capa-workflow/health"),
        ("ESG题库", "/api/v1/plugins/ddw-esg-question-bank/health"),
        ("Token管理", "/api/v1/plugins/ddw-token-manager/health"),
    ]:
        data = curl_json("GET", path)
        record("插件", name, PASS if data else FAIL, str(data)[:80] if data else "no response")

    # 3. 质量插件功能
    print("\n[3] 质量插件功能")
    spc = curl_json("POST", "/api/v1/plugins/ddw-spc-basic/capability",
                    {"data": [10.1, 10.2, 9.9, 10.0, 10.3, 9.8, 10.1, 10.0, 10.2, 9.9],
                     "lsl": 9.5, "usl": 10.5})
    record("质量", "SPC capability", PASS if spc and "cpk" in spc else FAIL, f"cpk={spc.get('cpk')}" if spc else "no response")

    qa = curl_json("POST", "/api/v1/plugins/ddw-quality-assistant/8d", {"problem": "test defect"})
    record("质量", "8D 生成", PASS if qa and qa.get("doc_type") == "8d" else FAIL)

    capa = curl_json("POST", "/api/v1/plugins/ddw-capa-workflow/capa",
                     {"title": "deploy-test", "description": "verify", "source": "audit", "severity": "medium"})
    record("质量", "CAPA 创建", PASS if capa and capa.get("capa_number") else FAIL, str(capa)[:80] if capa else "")

    # 4. 在线客服
    print("\n[4] 在线客服")
    chat = curl_json("POST", "/api/v1/plugins/ddw_online_cs/chat",
                     {"message": "你好，介绍一下DDW平台", "mode": "presales"})
    if chat:
        src = chat.get("source", "")
        ok = src == "kb+llm" and len(chat.get("answer", "")) > 20
        record("客服", "chat 回复", PASS if ok else WARN, f"source={src} len={len(chat.get('answer',''))}")
    else:
        record("客服", "chat 回复", FAIL, "no response")

    # 5. LLM 网关
    print("\n[5] LLM 网关")
    # ddw-llm-gateway 插件是 OpenAI 兼容网关：/v1/models 探活
    gw = curl_json("GET", "/v1/models")
    if gw and gw.get("data"):
        record("LLM", "网关 /v1/models", PASS, f"{len(gw['data'])} 模型")
    elif chat and chat.get("source") == "kb+llm":
        record("LLM", "网关", WARN, "客服 kb+llm 已间接证明 LLM 通道工作")
    else:
        record("LLM", "网关", FAIL, "无响应")

    # 6. 官网
    print("\n[6] 官网页面")
    for site, url in [("www", "https://www.9cio.com"), ("ddw", "https://ddw.9cio.com")]:
        code = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-m", "15", url],
            capture_output=True, text=True, timeout=20
        ).stdout.strip()
        record("官网", site, PASS if code == "200" else FAIL, f"HTTP {code}")

    # 7. HRIS（通过 MCP 注册日志验证）
    print("\n[7] HRIS 适配器")
    log_all = subprocess.run(
        ["journalctl", "-u", "ddw-core", "--no-pager", "-n", "400"],
        capture_output=True, text=True, timeout=15
    ).stdout
    if "ddw.hris.sync_employees" in log_all:
        record("HRIS", "MCP 工具注册", PASS, "ddw.hris.sync_employees 已注册")
    else:
        record("HRIS", "MCP 工具注册", FAIL, "日志中未找到")

    # 汇总
    print("\n" + "=" * 60)
    fails = [r for r in results if r[2] == FAIL]
    warns = [r for r in results if r[2] == WARN]
    print(f"汇总: {len(results) - len(fails) - len(warns)} 通过 / {len(warns)} 警告 / {len(fails)} 失败")
    if fails:
        print("\n❌ 失败项:")
        for f in fails:
            print(f"  - [{f[0]}] {f[1]}: {f[3]}")
    if warns:
        print("\n⚠️ 警告项:")
        for w in warns:
            print(f"  - [{w[0]}] {w[1]}: {w[3]}")
    print("=" * 60)
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
