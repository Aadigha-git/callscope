# Local concurrency / latency load (T-M6-01)

**Run ID:** `load-694f5a9867b5`
**Seed:** 42
**Public concurrency cap:** 2
**Knee (mock path):** None

## NFR-01 hypotheses

- p50 ≤ 1800 ms, p95 ≤ 3000 ms

## Results

| Concurrency | n | wall (s) | resp p50 | resp p95 | barge p50 | NFR-01 mock | projected p50 | NFR-01 projected |
|---:|---:|---:|---:|---:|---:|:---:|---:|:---:|
| 1 | 3 | 0.03 | 500 | 500 | — | yes | 3200 | no |
| 2 | 6 | 0.06 | 500 | 500 | — | yes | 3200 | no |

## Chart (response p95 vs concurrency)

```
c=1 |████████████████████████████████████████ 500 ms
c=2 |████████████████████████████████████████ 500 ms
```

## Session cap probe

- max_concurrent=2, acquired=2, overflow_blocked=True
- error: `max concurrent sessions (2) reached`

## Notes

- Transport: MockCallerTransport + synthetic agent events (CI-safe; not live demo).
- Mock agent first-audio offset is fixed (~500 ms) in runner_sim; NFR-01 mock check is structural.
- Projected e2e p50 adds Hermes turn p50 2700 ms (D-20260920-18) and cites TF TTFT p50 699 ms (D-20260920-17) as network floor.
- SessionCapLimiter max_concurrent=2; third acquire blocked=True.
- No latency knee at concurrency 1→2 on the mock path (oracle latencies are schedule-based, not CPU-bound).
- NFR-01 gap: projected p50 (mock local + Hermes turn) exceeds 1800 ms hypothesis — live Mac re-measure when demo stack is up.
