# Spike T-M0-07 — Mac sizing + Token Factory latency (S-6)

Throwaway harness under `spikes/T-M0-07/`. Results feed `docs/DECISIONS.md` and design §9.5.

## What was measured
1. **Machine baseline** — chip, RAM, usable budget (≥4 GB reserved)
2. **Native `livekit-server`** — Homebrew arm64 bottle, `--dev` on an alternate port
3. **Token Factory regional RTT** — 100 TCP + 20 HTTPS TTFB samples per region (no API key)
4. **Chat TTFT** — requires `TOKEN_FACTORY_API_KEY` (not in `.env` yet)

## Commands
```bash
python3 spikes/T-M0-07/scripts/mac_baseline.py

# Native LiveKit (7880 may be occupied by Docker; use another port)
livekit-server --dev --config-body "port: 17880"

# Network only (no spend)
python3 spikes/T-M0-07/scripts/probe_tf_latency.py \
  --samples 100 --https-samples 20 --skip-chat \
  --out spikes/T-M0-07/results/tf_latency.json

# After setting TOKEN_FACTORY_API_KEY in .env (cap spend):
set -a && source .env && set +a
python3 spikes/T-M0-07/scripts/probe_tf_latency.py \
  --skip-network --samples 100 --max-usd 0.25 \
  --out spikes/T-M0-07/results/tf_chat_ttft.json
```

## Results (this run)
See `results/mac_baseline.json`, `results/tf_latency.json`, `results/SUMMARY.md`.
