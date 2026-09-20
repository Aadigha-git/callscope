# T-M0-03 / S-2 SUMMARY — Hermes TTFT overhead vs Token Factory direct

**Run ID (baseline):** `6a3855de-f0f2-45e4-906a-5af9defb2c49`
**Model:** `nvidia/Nemotron-3_5-Lightning` (D-20260920-18)
**Turns:** 50 each path · stream=true · slim spoken system prompt · empty toolset
**Spend:** ~**$0.006** (under $1 cap)
**Hermes:** 0.19.0 API server (`gateway run`)

## Results

| Path | TTFT p50 | TTFT p95 | Mean prompt tokens | Est. USD |
|---|---:|---:|---:|---:|
| Token Factory **direct** | **884 ms** | 989 ms | ~47 | ~0.0009 |
| **Hermes → TF** | **2287 ms** | 3779 ms | ~507 | ~0.0054 |
| **Overhead (Hermes − direct)** | **1385 ms** | 2907 ms | +~460 tokens | — |

## Verdict vs design §3.6 / U2

- Hermes-own overhead budget (S-2): **p50 ≤ 450 ms** → **FAIL** (measured **1385 ms**).
- Absolute Hermes TTFT p50 **~2.3 s** already exceeds NFR-01 end-to-end p50 **1.8 s** before ASR/TTS.
- Root cause: Hermes injects a large default agent system/skills context (~507 prompt tokens vs ~47 direct) even with `platform_toolsets.api_server: []` and `memory.memory_enabled: false` (mitigation re-check, 20 turns: overhead p50 still ~1.8 s; tokens still ~507).

## Mitigation (R-02) — accepted

1. **Thin FAQ / chitchat fast-path** in the voice worker: call Token Factory (or a tiny local reply) **without** Hermes for turns that need no tools.
2. **Hermes only for tool/plan turns** (book/reschedule/cancel/callback/handoff).
3. Continue stripping Hermes profile in T-M1-09 (receptionist profile); measure again after lock-down.

Do **not** claim the original local-vLLM 350–450 ms Hermes→token row for hosted TF without this split.

## Raw

- `results/ttft_overhead.json` (baseline 50)
- `results/ttft_overhead_slim_memory_off.json` (mitigation attempt)
