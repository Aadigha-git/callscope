# T-M0-07 / S-6 summary

Captured **2026-09-20** on developer Mac (Los Angeles / Irvine area).

## Machine
| Field | Value |
|---|---|
| Chip | Apple M5 |
| Arch | arm64 |
| RAM | 16.0 GB unified |
| OS | macOS 26.6.2 (25G83) |
| Reserve (OS/browser) | ≥ 4 GB |
| Usable for models (estimate) | ≈ 12 GB |
| Approx free+purgeable at capture | ~0.16 GB (machine was busy; not a capacity limit) |

ASR/TTS/VAD memory + RTF: **deferred to T-M0-06 (S-5)** — no downloads >2 GB in this spike.

## Native livekit-server
| Field | Value |
|---|---|
| Install | `brew install livekit` → **1.13.7** |
| Binary | `/opt/homebrew/bin/livekit-server` — **Mach-O arm64** |
| Dev mode | `livekit-server --dev --config-body "port: 17880"` → HTTP **200** |
| Default keys | `devkey` / `secret` |
| Note | Port **7880** was already bound by Docker Desktop (published LiveKit from an earlier spike). Native server works on an alternate port; for `make demo`, stop the container or bind native to 7880. |
| Fallback | Not needed. FastAPI WebSocket ADR **not** drafted. |

## Token Factory network RTT (no API key)
100 TCP samples + 20 HTTPS TTFB samples per region.

| Region | Host | TCP p50 (ms) | TCP p95 (ms) | HTTPS p50 (ms) | HTTPS p95 (ms) |
|---|---|---:|---:|---:|---:|
| **us-central1** | `api.tokenfactory.us-central1.nebius.com` | **49.8** | **66.1** | **198.6** | **221.5** |
| eu-west1 | `api.tokenfactory.eu-west1.nebius.com` | 150.7 | 167.2 | 620.9 | 701.3 |
| eu-north1 | `api.tokenfactory.nebius.com` | 191.0 | 205.0 | 763.7 | 900.1 |

**Chosen region (network):** `us-central1` (~4× lower TCP p50 than eu-north1).

Catalog note: many cheap FC models (Qwen3-30B, Nemotron Nano, gpt-oss-120b) list **eu-north1** in the public catalog. Prefer a **us-central1**-hosted flavor when available; otherwise accept ~190 ms TCP floor to eu-north1 and measure chat TTFT on the model you actually use (T-M0-04).

## Chat completion latency (100 requests)
Model: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` via `https://api.tokenfactory.nebius.com/v1/`
(non-streaming end-to-end; tiny prompt “Reply with exactly: ok”, max_tokens=4)

| Metric | Value |
|---|---|
| Completed / errors | **100 / 0** |
| Latency p50 | **699 ms** |
| Latency p95 | **824 ms** |
| Mean / min / max | 719 / 677 / 885 ms |
| Tokens | 2100 prompt + 400 completion |
| Estimated spend | **~$0.00022** (cap was $0.25) |

Raw: `tf_chat_ttft.json`. Implication for NFR-01 (p50 ≤ 1.8 s e2e): brain+network alone already ~0.7 s on this tiny call to the default (eu-north1) endpoint — leave headroom for ASR/TTS; prefer us-central1-hosted models when available (T-M0-04).

## Memory budget (§9.5)
| Item | Measured / plan |
|---|---|
| ASR | *T-M0-06* |
| TTS | *T-M0-06* |
| VAD (Silero) | *T-M0-06* / Agents |
| Hermes + worker + APIs | measure in M1 walking skeleton |
| Optional local LLM | likely deferred on 16 GB with ASR+TTS |
| Headroom | ≥4 GB reserved |
