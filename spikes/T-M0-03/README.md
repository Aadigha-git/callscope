# Spike T-M0-03 — Hermes per-turn overhead vs Token Factory (S-2)

```bash
cd spikes/T-M0-03
# reuse T-M0-04 hermes venv or: uv venv && uv pip install -r requirements.txt
ln -sfn ../T-M0-04/.venv .venv
set -o pipefail
.venv/bin/python scripts/run_ttft_probe.py --limit 50 --max-usd 1.0
```

Results: `results/SUMMARY.md`, `results/ttft_overhead.json`.
