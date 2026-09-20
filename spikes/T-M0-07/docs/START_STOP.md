# Local demo start/stop (input to T-M6-03)

## Prerequisites
- Apple Silicon Mac; Homebrew; Docker Desktop for Postgres/Prometheus/Grafana only
- `uv sync`; `.env` from `.env.example` with `TOKEN_FACTORY_API_KEY` when using live LLM

## LiveKit (native)
```bash
# If nothing is on 7880:
livekit-server --dev

# If Docker already published 7880, either stop that container or:
livekit-server --dev --config-body "port: 17880"
# and point CALLSCOPE_LIVEKIT_URL at the matching port.
```
Dev credentials: API key `devkey`, secret `secret` (LiveKit `--dev` defaults).

## Data plane
```bash
make dev-up    # Postgres, MinIO, Prometheus, Grafana
make dev-down
```

## Full demo (after T-M1-11)
```bash
make demo      # Compose + native Procfile processes
make demo-stop
```

## Notes
- ASR/TTS/Hermes/worker must run **natively** (no Metal in Docker Desktop).
- LLM: Token Factory over HTTPS; optional local mlx-lm/llama.cpp later.
- No GPU VM start/stop; no idle GPU shutdown.
