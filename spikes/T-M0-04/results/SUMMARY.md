# T-M0-04 / S-3 SUMMARY — Token Factory + Hermes tool-call reliability

**Run ID:** `394d90d9-702a-44db-b081-be6ee0879428`
**UTC:** 2026-09-20T22:32:26Z (approx; see `tool_reliability.json`)
**Hermes:** `hermes-agent==0.19.0` (PyPI)
**Path:** Hermes API server (`gateway run` + `API_SERVER_*`) → custom provider → Token Factory
**Base URL:** `https://api.tokenfactory.nebius.com/v1/`
**Scenarios:** 60 scripted Lakeside turns (`scripts/scenarios.py`)
**Toolset lockdown:** `platform_toolsets.api_server: [callscope-s3]` (stub tools only)
**Total estimated spend:** **~$0.080** (usage-based; under $2 cap)

## Results

| Model | Licence | $/1M in | $/1M out | Valid rate | Schema-ok | Injection OK | p50 latency | Est. USD |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **nvidia/Nemotron-3_5-Lightning** (winner) | OpenMDW v1.1 | 0.06 | 0.24 | **100%** (60/60) | 100% | 100% | ~2726 ms | ~0.024 |
| Qwen/Qwen3-30B-A3B-Instruct-2507 | Apache 2.0 | 0.10 | 0.30 | **100%** (60/60) | 100% | 100% | ~4767 ms | ~0.026 |
| nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B | nvidia-open-model-license | 0.06 | 0.24 | **98.3%** (59/60) | 100%* | 100% | ~10767 ms | ~0.031 |

\*Nano failure: `book_missing_1` returned no tool call (spoken clarification only). All three models ≥95% gate.

## Verdict

Choose **`nvidia/Nemotron-3_5-Lightning`** as the demo agent LLM on Token Factory: perfect scripted tool-call rate, lowest spend in this run, lowest Hermes-turn p50 among candidates that hit 100%.

Keep **Qwen3-30B-A3B-Instruct-2507** as alternate (Apache 2.0; also 100%). Nano remains a cost/latency fallback if Lightning is unavailable in-region.

## Hermes notes (verified against 0.19.0)

- Custom provider: `model.provider: custom` + `base_url` + `api_key` (same pattern as T-M0-02).
- Plugin tools: `register_tool(..., toolset="callscope-s3")`; handlers receive `(args: dict, **kwargs)` and must return a **JSON string**.
- API server needs `aiohttp` installed (optional extra / explicit pin in spike requirements).

## Local fallback

Sketch only: `docs/local_fallback.md` (mlx-lm / llama.cpp). Not measured this spike.

## Raw

- `results/tool_reliability.json`
- `ENVIRONMENT.md`
- Hermes logs gitignored under `results/*.log`
