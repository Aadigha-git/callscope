# Spike T-M0-04 — LLM shortlist tool-call reliability (S-3)

Throwaway probe: configure Hermes Agent → Nebius Token Factory (custom
OpenAI-compatible provider) and measure valid tool-call rate on ~60 scripted
Lakeside Home Services receptionist turns with stub tools.

## Environment

See `ENVIRONMENT.md` (written by the harness). Pinned: `hermes-agent==0.19.0`.

## Layout

| Path | Role |
|---|---|
| `plugin/` | Stub receptionist tools + hook logger |
| `scripts/scenarios.py` | ~60 scripted turns |
| `scripts/run_tool_probe.py` | Hermes home setup, gateway, scoring |
| `docs/local_fallback.md` | Optional mlx-lm / llama.cpp sketch (not a gate) |
| `results/` | Scrubbed JSON + SUMMARY |

## Rerun

```bash
cd spikes/T-M0-04
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
# TOKEN_FACTORY_API_KEY from repo .env or environment
.venv/bin/python scripts/run_tool_probe.py --max-usd 2.0
```

Smoke (2 turns, one model):

```bash
.venv/bin/python scripts/run_tool_probe.py --limit 2 \
  --models nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B --max-usd 0.05
```

Do not import this into `callscope/` or `plugins/hermes_callscope/`.
