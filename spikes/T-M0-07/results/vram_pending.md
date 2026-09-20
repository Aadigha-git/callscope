# VRAM / warm-up — PENDING GPU NODE

Acceptance requires measured VRAM replacing design §9.5 and warm-up minutes.
No CUDA device on the developer laptop (`nvidia-smi` absent). Nebius CLI not installed.

| Item | Status |
|---|---|
| Idle / per-service VRAM | **Blocked** — run `scripts/measure_vram.py` on the node |
| Cold vs warm model load | **Blocked** — needs persistent cache mount + model images |
| Warm-up minutes (instance start → ready) | **Blocked** — measure during first `START_STOP.md` start |

Placeholder table (estimates unchanged until measured):

| Item | Approx. VRAM (design estimate) | Measured |
|---|---|---|
| LLM 7–9B quantised | 5–10 GB | TBD |
| KV cache ~3 sessions | 4–8 GB | TBD |
| ASR | 2–4 GB | TBD |
| TTS | 1–3 GB | TBD |
| Headroom | 20% | TBD |
| Idle baseline | — | TBD |

Operator checklist once VM is up:

1. `bash scripts/bootstrap_gpu_node.sh | tee results/bootstrap.txt`
2. Mount persistent disk at `/var/lib/callscope/models`
3. `python3 scripts/measure_vram.py --mode probe-idle --out results/vram_idle.json`
4. Load real services when images exist; record wall times in `results/warmup.md`
