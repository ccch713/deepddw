#!/usr/bin/env python3
"""deepDDW 并发压测（P2-2）——5/10/20 设备并发场景延迟/错误率。

用法:
    python scripts/load_test/load_test.py --url http://127.0.0.1:8500 \
        --token <DDW_ACCESS_TOKEN> --devices 5,10,20 --rounds 3

行为（每档设备数跑 rounds 轮）:
    1. 每"设备"注册（/device/register，幂等）
    2. 并发：每设备连续发 N 个 chat 请求（rag=false）+ 记忆写入
       （/memory/logs append）
    3. 统计: 总请求数 / 成功数 / 429 / 503 / 5xx / P50 / P95 / 错误率
产出: 终端表格 + scripts/load_test/results.json（可复跑）

注意: chat 无 LLM key 时返回降级响应（仍 200），压的是网关+SQLite 链路；
      有 DeepSeek key 时测真实 LLM 链路（更慢，可调低 --req-per-device）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx

BASE = ""


async def _register(client: httpx.AsyncClient, device_id: str, token: str) -> None:
    try:
        await client.post(
            f"{BASE}/api/v1/device/register",
            headers={"X-DDW-Token": token},
            json={"device_id": device_id, "device_name": f"压测-{device_id[-4:]}"},
        )
    except Exception:  # noqa: BLE001
        pass


async def _device_loop(
    client: httpx.AsyncClient, device_id: str, token: str,
    reqs: int, latencies: List[float], errors: Dict[str, int],
    success: List[int],
) -> None:
    """单设备：reqs 个 chat + 记忆写入，统计延迟/错误。

    latencies 只记 chat 延迟（P95 关注对话响应）；success 计数含 chat+memory
    两个请求（只要任一非 200 都计错误）。
    """
    for i in range(reqs):
        try:
            t0 = time.perf_counter()
            r = await client.post(
                f"{BASE}/api/v1/chat/",
                headers={"X-DDW-Token": token},
                json={"message": f"设备 {device_id[-4:]} 并发请求 {i}",
                      "rag": False, "auto_consolidate": False},
            )
            if r.status_code != 200:
                errors[r.status_code] = errors.get(r.status_code, 0) + 1
            else:
                latencies.append((time.perf_counter() - t0) * 1000)
                success[0] += 1
            # 记忆写入（SQLite 并发写场景）
            r2 = await client.post(
                f"{BASE}/api/v1/memory/logs",
                headers={"X-DDW-Token": token},
                json={"content": f"压测 {device_id[-4:]} #{i}", "auto": True},
            )
            if r2.status_code != 200:
                errors[r2.status_code] = errors.get(r2.status_code, 0) + 1
            else:
                success[0] += 1
        except Exception:  # noqa: BLE001  # 连接级错误记为 0 状态
            errors[0] = errors.get(0, 0) + 1


async def _run_round(
    url: str, token: str, n_devices: int, reqs_per_device: int,
) -> Dict[str, Any]:
    """一轮 n 设备并发。"""
    global BASE
    BASE = url
    latencies: List[float] = []
    errors: Dict[str, int] = {}
    timeout = httpx.Timeout(30.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        device_ids = [f"load-{n_devices}-{i:04d}" for i in range(n_devices)]
        for did in device_ids:
            await _register(client, did, token)
        t_start = time.perf_counter()
        success_counter: List[int] = [0]
        await asyncio.gather(*[
            _device_loop(client, did, token, reqs_per_device, latencies, errors,
                         success_counter)
            for did in device_ids
        ])
        success_count = success_counter[0]
        elapsed = time.perf_counter() - t_start

    total = n_devices * reqs_per_device * 2  # chat + memory
    success = success_count
    err_total = sum(errors.values())
    p50 = statistics.median(latencies) if latencies else 0
    p95 = 0.0
    if latencies:
        srt = sorted(latencies)
        p95 = srt[min(len(srt) - 1, int(len(srt) * 0.95))]
    return {
        "devices": n_devices,
        "requests": total,
        "success": success,
        "errors": err_total,
        "error_rate": round(err_total / total * 100, 2) if total else 0,
        "error_codes": errors,
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
        "elapsed_s": round(elapsed, 2),
        "rps": round(total / elapsed, 1) if elapsed else 0,
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description="deepDDW 并发压测")
    ap.add_argument("--url", default="http://127.0.0.1:8500")
    ap.add_argument("--token", required=True)
    ap.add_argument("--devices", default="5,10,20")
    ap.add_argument("--rounds", type=int, default=3, help="每档轮数")
    ap.add_argument("--req-per-device", type=int, default=5)
    ap.add_argument("--out", default=str(Path(__file__).parent / "results.json"))
    args = ap.parse_args()

    device_list = [int(x) for x in args.devices.split(",") if x.strip()]
    print(f"压测目标 {args.url} · 设备档 {device_list} · {args.rounds} 轮/档\n")
    all_results: Dict[str, Any] = {
        "target": args.url,
        "devices_per_round": device_list,
        "rounds": args.rounds,
        "req_per_device": args.req_per_device,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "rounds_data": {},
        "aggregate": {},
    }
    header = f"{'设备数':>6} {'请求':>6} {'成功':>6} {'错误':>5} {'错误率%':>7} {'P50ms':>7} {'P95ms':>7} {'RPS':>6}"
    print(header)
    print("-" * len(header))
    for nd in device_list:
        round_rows = []
        for r in range(args.rounds):
            row = await _run_round(args.url, args.token, nd, args.req_per_device)
            round_rows.append(row)
        # 聚合（取各轮均值）
        agg = {
            "devices": nd,
            "requests": row["requests"],
            "success_avg": round(sum(x["success"] for x in round_rows) / len(round_rows), 1),
            "error_rate_avg": round(sum(x["error_rate"] for x in round_rows) / len(round_rows), 2),
            "p50_avg_ms": round(sum(x["p50_ms"] for x in round_rows) / len(round_rows), 1),
            "p95_avg_ms": round(sum(x["p95_ms"] for x in round_rows) / len(round_rows), 1),
            "rps_avg": round(sum(x["rps"] for x in round_rows) / len(round_rows), 1),
        }
        all_results["rounds_data"][str(nd)] = round_rows
        all_results["aggregate"][str(nd)] = agg
        print(f"{nd:>6} {agg['requests']:>6} {agg['success_avg']:>6} "
              f"{round(agg['requests'] - agg['success_avg']):>5} "
              f"{agg['error_rate_avg']:>7} {agg['p50_avg_ms']:>7} "
              f"{agg['p95_avg_ms']:>7} {agg['rps_avg']:>6}")

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已写入 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
