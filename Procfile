# Native demo processes (honcho). Data plane stays in docker-compose.local.yml.
# Start: make demo   Stop: make demo-stop
# Requires: brew install livekit; uv sync --extra dev; apps/web npm install (auto in demo_start).

livekit: livekit-server --dev --bind 127.0.0.1
api: uv run python -m apps.api
asr: uv run python -m servers.asr
tts: uv run python -m servers.tts
worker: uv run python -m apps.worker --serve
web: sh -c 'cd apps/web && npm run dev -- --host 127.0.0.1 --port 5173'
