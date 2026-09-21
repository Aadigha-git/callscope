# Hermes receptionist profile (T-M1-09)

Local Hermes Agent API server for CallScope. Config keys verified against
`hermes-agent` 0.19.0 spikes (T-M0-02 / T-M0-03 / T-M0-04).

## Layout

| Path | Purpose |
|------|---------|
| `config.yaml` | Model (Token Factory custom provider), plugins, toolset lockdown, memory off |
| `.env.example` | `API_SERVER_*` + TF keys (copy beside `HERMES_HOME`) |
| `toolset_allowlist.txt` | Allowed `platform_toolsets.api_server` entries |
| `toolset_selftest.py` | Fail closed if config allowlist drifts |

## Run (local)

```bash
export HERMES_HOME=/path/to/this/dir   # or copy files into a dedicated HERMES_HOME
# Fill Token Factory key in .env (never commit)
hermes gateway run --accept-hooks
# API: http://127.0.0.1:8642  (API_SERVER_PORT)
```

Worker / `HermesBackend` posts to `POST /v1/chat/completions` with `stream=true`,
`Authorization: Bearer $API_SERVER_KEY`, and `CALL_CONTEXT call_id=…` in **user**
message content (D-20260920-04).

## Toolset lockdown

`platform_toolsets.api_server` must be **only** `callscope-receptionist`
(future `hermes-callscope` plugin toolset). Never `hermes-api-server` (would enable
terminal/file/browser tools).

```bash
python infra/hermes/toolset_selftest.py --config infra/hermes/config.yaml
```

## Optional local LLM fallback

Point `model.base_url` at mlx-lm / llama.cpp OpenAI-compatible `:8080/v1`
(see `spikes/T-M0-04/docs/local_fallback.md`). Re-measure tool-calling; do not
assume Token Factory scores. Avoid Ollama as primary (Hermes stream+tools risk).
