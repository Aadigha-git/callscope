# Spike T-M0-05 — LiveKit Agents wiring + hermes-livekit comparison (S-4)

Throwaway probe under `spikes/T-M0-05/` only. Do not import into `callscope/`.

## Verdict (summary)

- **Own LiveKit Agents worker** with CallScope provider adapters is the right path
  (ADR-002 confirmed / refined — see D-20260920-05).
- **Do not adopt** third-party `hermes-livekit` on the public path without an explicit
  product decision (gaps vs FR-06 instrumentation; requires Hermes ≥0.20.0 which is
  not on PyPI yet; MIT licence OK).
- Config mapping for design §4.2 → `livekit-agents==1.8.2` is in
  `results/config_mapping.md`.

## Versions (recorded)

See `ENVIRONMENT.md`.

| Component | Version |
|---|---|
| livekit-agents[+silero] | 1.8.2 |
| livekit (Python RTC) | 1.1.18 |
| livekit-api | 1.2.1 |
| livekit-server (Docker) | v1.9.1 |
| hermes-livekit (reviewed) | 0.4.0 @ `640812f` (GitHub kortexa-ai/hermes-livekit) |

## Layout

| Path | Role |
|---|---|
| `docker-compose.yml` | local `livekit-server --dev` (keys `devkey`/`secret`) |
| `agent/worker.py` | minimal AgentServer + stub providers |
| `agent/stubs.py` | EchoSTT, CannedLLM, SineTTS |
| `web/index.html` | browser join UI (`livekit-client` CDN) |
| `scripts/mint_token.py` | JWT + `RoomAgentDispatch` |
| `scripts/smoke_call.py` | headless join + publish tone; asserts agent audio |
| `results/` | mapping, barge-in notes, hermes-livekit review, evidence |

## Rerun

```bash
cd spikes/T-M0-05
docker compose up -d
uv python install 3.12
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -r requirements.txt

export LIVEKIT_URL=ws://127.0.0.1:7880 LIVEKIT_API_KEY=devkey LIVEKIT_API_SECRET=secret
python agent/worker.py start   # or: python agent/worker.py dev

# other terminal
python scripts/smoke_call.py
# expect: SMOKE_OK agent_audio_subscribed

# browser
python scripts/mint_token.py   # paste TOKEN into web/index.html
python -m http.server 8765 --directory web
# open http://127.0.0.1:8765/
```

Tokens **must** include `RoomConfiguration(agents=[RoomAgentDispatch(agent_name="")])`
or the unnamed worker will not be dispatched (observed during this spike).

## Barge-in

Framework defaults + design-mapped knobs exercised via smoke (agent greets immediately
with interruptible TTS). Manual browser: speak over the greeting tone; with
`interruption.min_duration=0.25` and `aec_warmup_duration=0.4`, brief echo at playback
start should be suppressed. Notes: `results/barge_in_notes.md`.
