# Load-Test Report — Multi-Device Concurrency (0.2.0)

> Method: `scripts/load_test/load_test.py` — re-runnable async load script
> (httpx), simulating N devices doing chat + memory writes through the gateway.
> Tested on the 16 GB test machine; independently re-run by the QA instance
> (same script) with matching results.

## Results

| Devices | Requests | Errors | Error % | P50 | P95 | RPS |
|---------|----------|--------|---------|-----|-----|-----|
| 5   | 50  | 0 | 0% | 12.2 ms  | 35.6 ms  | 600 |
| 10  | 100 | 0 | 0% | 26.6 ms  | 57.5 ms  | 595 |
| 20  | 200 | 0 | 0% | 52.0 ms  | 126.0 ms | 607 |

QA re-run (2 rounds/level, same script): 0% errors at all levels; P95 45.7 / 117.1 ms
for 10 / 20 devices; **no `database is locked` observed** — consistent with the
20-concurrent-writer unit test.

## Conclusion

20 devices chatting + writing memory concurrently: **zero errors, P95 126 ms,
no SQLite lock conflicts** — the "up to 20 devices on your LAN" claim is backed
by measured data.

## Re-run

```bash
# disable rate limiting to isolate raw concurrency behavior
DDW_RATE_LIMIT_ENABLED=false python scripts/load_test/load_test.py \
  --url http://<host>:8500 --token <token> --devices 5,10,20 --rounds 3
```

Note: the load test exercises the gateway + SQLite path (chat degrades gracefully
without an LLM key). With a real LLM provider the chat path is slower — lower the
concurrency accordingly.
