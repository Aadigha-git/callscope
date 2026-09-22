# Demo runbook (interview / screen-share)

**Goal:** Interviewer sees a live local CallScope call in under ~20 minutes (NFR-07).

**Scope:** Apple Silicon Mac. No public GPU VM. LLM via Nebius Token Factory (budgeted)
or cassette replay. Never point load tests at a live demo window.

## Once per machine

```bash
git clone <repo> && cd callscope
make setup                  # uv + hooks; copies .env.example → .env
brew install livekit        # livekit-server
# Edit .env: TOKEN_FACTORY_API_KEY if using live brain; else keep cassette replay
```

Optional (full brain path): install Hermes API server + `infra/hermes` profile;
`make hermes-selftest` must pass.

## Start

```bash
make demo                   # Compose + honcho — **leave this terminal open**
# Wait until you see "registered worker" in the honcho output
open http://127.0.0.1:5173  # web client
open http://127.0.0.1:3000  # Grafana (admin / $GRAFANA_ADMIN_PASSWORD)
```

`make demo` now runs **in the foreground**. Do not Ctrl-C until you are done —
backgrounding used to drop LiveKit (`:7880`) while the UI still looked "online".

| URL | What |
|-----|------|
| http://127.0.0.1:5173 | Consent + live call (WebRTC → LiveKit) |
| http://127.0.0.1:8000/v1/status | API online / session cap |
| http://127.0.0.1:8501 | Review console (`make review` separately) |
| http://127.0.0.1:3000 | Live-ops + quality dashboards |

Default ASR/TTS use **mlx_whisper + piper** when `uv sync --extra native` is installed and
the Piper voice exists under `data/models/piper/`. Otherwise `make demo` falls back to fake
(so honcho does not tear down the UI).

```bash
uv sync --extra native --extra worker --extra dev
# Piper voice (~61 MB, once):
mkdir -p data/models/piper
curl -L -o data/models/piper/en_US-lessac-medium.onnx \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
curl -L -o data/models/piper/en_US-lessac-medium.onnx.json \
  https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json
# .env: TOKEN_FACTORY_API_KEY=…  CALLSCOPE_ASR_BACKEND=mlx_whisper  CALLSCOPE_TTS_BACKEND=piper
# CALLSCOPE_LIVEKIT_API_SECRET=secret   # must match livekit-server --dev
make demo
```

## Interviewer script (≈3 minutes)

1. Show fictional-data / consent banner on the web client; accept consent.
2. Start a call; say a booking request (e.g. “I’d like an appointment Friday morning”).
3. Show barge-in: talk over the agent; playback should stop quickly.
4. End the call; open Grafana Live-ops (active calls / latency).
5. Optional: `make review` + seed-demo for RCA / labels.
6. Point to the [static showcase](../showcase/index.html) for eval CIs, model card, load report.

## Stop / kill switch

```bash
make demo-stop
```

If a session is stuck minting: set `CALLSCOPE_WORKER_ONLINE=false` and restart API, or
`make demo-stop`. Rotate `CALLSCOPE_SERVICE_TOKEN` / LiveKit keys if exposed.

## Budget

```bash
make budget
```

Live Token Factory needs `--live` on eval paths and must stay under
`CALLSCOPE_LLM_BUDGET_USD`. Prefer cassettes for CI and rehearsals.

## Smoke without browser

```bash
make eval ARGS='run --mode caller_sim --stack mock'
make load
make security-test
```

## Record the demo video

Follow [docs/showcase/VIDEO.md](../showcase/VIDEO.md). Commit or attach the file under
`docs/showcase/assets/` (large binaries: Git LFS or release asset — see D-20260922-47).
