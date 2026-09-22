#!/usr/bin/env bash
# Start Compose data plane + native Procfile processes (T-M1-11).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STATE_DIR="${CALLSCOPE_DEMO_STATE:-$ROOT/.demo}"
mkdir -p "$STATE_DIR"

echo "==> Compose data plane (Postgres, MinIO, Prometheus, Grafana)"
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker is not running. Start Docker Desktop, then re-run make demo." >&2
  exit 1
fi
docker compose -f docker-compose.local.yml up -d

echo "==> Waiting for Postgres..."
for _ in $(seq 1 30); do
  if docker compose -f docker-compose.local.yml exec -T postgres pg_isready -U callscope >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! command -v livekit-server >/dev/null 2>&1; then
  echo "ERROR: livekit-server not found. Install with: brew install livekit" >&2
  exit 1
fi

if ! command -v honcho >/dev/null 2>&1 && ! uv run honcho --help >/dev/null 2>&1; then
  echo "ERROR: honcho not found. Run: uv sync --extra dev" >&2
  exit 1
fi

# Any leftover native process on a Procfile port makes that process crash;
# honcho then SIGTERMs the whole voice stack (web/API die together).
_free_demo_ports() {
  local port pids
  for port in 7880 8000 8100 8200 8300 5173 9100; do
    pids="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      echo "==> Port $port busy; freeing (pids: $pids)"
      # shellcheck disable=SC2086
      kill -TERM $pids 2>/dev/null || true
    fi
  done
  sleep 1
  for port in 7880 8000 8100 8200 8300 5173 9100; do
    pids="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      # shellcheck disable=SC2086
      kill -KILL $pids 2>/dev/null || true
    fi
  done
}
_free_demo_ports

# Port 7880 must also be free of spike LiveKit containers (not just native PIDs).
if lsof -nP -iTCP:7880 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "==> Port 7880 still busy; trying to stop spike LiveKit (spikes/T-M0-05)..."
  if [[ -f spikes/T-M0-05/docker-compose.yml ]]; then
    docker compose -f spikes/T-M0-05/docker-compose.yml down >/dev/null 2>&1 || true
  fi
  sleep 1
fi
if lsof -nP -iTCP:7880 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "ERROR: port 7880 still in use — native livekit-server cannot start," >&2
  echo "       and honcho will tear down the whole voice stack (web/API dead)." >&2
  echo "Holding process:" >&2
  lsof -nP -iTCP:7880 -sTCP:LISTEN >&2 || true
  docker ps --format 'table {{.Names}}\t{{.Ports}}\t{{.Image}}' 2>/dev/null | grep 7880 >&2 || true
  echo "Fix: docker compose -f spikes/T-M0-05/docker-compose.yml down" >&2
  echo "  or: make demo-stop && make demo" >&2
  exit 1
fi
# Fail fast on other Procfile ports still held (e.g. Docker-owned).
for port in 8000 8100 8200 8300 5173; do
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "ERROR: port $port still in use after cleanup — honcho would abort." >&2
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >&2 || true
    echo "Fix: make demo-stop && make demo" >&2
    exit 1
  fi
done

if [[ ! -d apps/web/node_modules ]]; then
  echo "==> npm install (apps/web)"
  (cd apps/web && npm install)
fi

export CALLSCOPE_METRICS_PORT="${CALLSCOPE_METRICS_PORT:-9100}"

# Prefer real ASR/TTS when packages are available (user wants a live call).
if uv run python -c "import mlx_whisper" >/dev/null 2>&1; then
  export CALLSCOPE_ASR_BACKEND="${CALLSCOPE_ASR_BACKEND:-mlx_whisper}"
else
  export CALLSCOPE_ASR_BACKEND="${CALLSCOPE_ASR_BACKEND:-fake}"
fi
if uv run python -c "import piper" >/dev/null 2>&1; then
  export CALLSCOPE_TTS_BACKEND="${CALLSCOPE_TTS_BACKEND:-piper}"
else
  export CALLSCOPE_TTS_BACKEND="${CALLSCOPE_TTS_BACKEND:-fake}"
fi

# Missing native ASR/TTS packages crash uvicorn → honcho SIGTERMs web/API too.
_asr="$CALLSCOPE_ASR_BACKEND"
_tts="$CALLSCOPE_TTS_BACKEND"
if [[ "$_asr" == "mlx_whisper" ]]; then
  if ! uv run python -c "import mlx_whisper" >/dev/null 2>&1; then
    echo "WARN: mlx_whisper not installed → falling back to CALLSCOPE_ASR_BACKEND=fake" >&2
    echo "      Install: uv sync --extra native" >&2
    export CALLSCOPE_ASR_BACKEND=fake
  fi
fi
if [[ "$_tts" == "piper" ]]; then
  if ! uv run python -c "import piper" >/dev/null 2>&1; then
    echo "WARN: piper not installed → falling back to CALLSCOPE_TTS_BACKEND=fake" >&2
    echo "      Install: uv sync --extra native (+ voice under data/models/piper/)" >&2
    export CALLSCOPE_TTS_BACKEND=fake
  fi
  if [[ ! -f data/models/piper/en_US-lessac-medium.onnx ]]; then
    echo "WARN: Piper voice missing at data/models/piper/en_US-lessac-medium.onnx" >&2
    echo "      Download or set CALLSCOPE_PIPER_ONNX; falling back to fake TTS" >&2
    export CALLSCOPE_TTS_BACKEND=fake
  fi
fi
if [[ "$_tts" == "kokoro_onnx" || "$_tts" == "kokoro" ]]; then
  if ! uv run python -c "import kokoro_onnx" >/dev/null 2>&1; then
    echo "WARN: kokoro_onnx not installed → falling back to CALLSCOPE_TTS_BACKEND=fake" >&2
    export CALLSCOPE_TTS_BACKEND=fake
  fi
fi

# LiveKit Agents worker reads LIVEKIT_* (map from CallScope names).
set -a
# shellcheck disable=SC1091
[[ -f .env ]] && source .env
set +a
export LIVEKIT_URL="${LIVEKIT_URL:-${CALLSCOPE_LIVEKIT_URL:-ws://127.0.0.1:7880}}"
export LIVEKIT_API_KEY="${LIVEKIT_API_KEY:-${CALLSCOPE_LIVEKIT_API_KEY:-devkey}}"
export LIVEKIT_API_SECRET="${LIVEKIT_API_SECRET:-${CALLSCOPE_LIVEKIT_API_SECRET:-secret}}"
export CALLSCOPE_ASR_URL="${CALLSCOPE_ASR_URL:-http://127.0.0.1:8200}"
export CALLSCOPE_TTS_URL="${CALLSCOPE_TTS_URL:-http://127.0.0.1:8300}"

_tf_key="${TOKEN_FACTORY_API_KEY-}"
_nb_key="${NEBIUS_API_KEY-}"
if [[ -z "${_tf_key}${_nb_key}" ]]; then
  echo "WARN: TOKEN_FACTORY_API_KEY unset — agent LLM will fail on first turn." >&2
  echo "      Put the key in .env for a real conversation." >&2
fi
unset _tf_key _nb_key

echo "==> Native processes via honcho (Procfile)"
echo "    ASR_BACKEND=$CALLSCOPE_ASR_BACKEND  TTS_BACKEND=$CALLSCOPE_TTS_BACKEND"
chmod +x scripts/livekit_wrap.sh

# Foreground when the user runs `make demo` in a real terminal — that keeps
# LiveKit alive for the whole session. Background only for non-TTY /
# CALLSCOPE_DEMO_BG=1 (agents/CI).
if [[ -t 1 && "${CALLSCOPE_DEMO_BG:-}" != "1" ]]; then
  echo "==> Foreground mode — leave this terminal open (Ctrl-C to stop)."
  echo "    Then open http://127.0.0.1:5173"
  exec uv run honcho start -f Procfile
fi

echo "==> Background mode (CALLSCOPE_DEMO_BG=1 or non-TTY)"
(
  trap '' HUP
  exec uv run honcho start -f Procfile
) </dev/null >"$STATE_DIR/honcho.log" 2>&1 &
echo $! >"$STATE_DIR/honcho.pid"
disown "$(cat "$STATE_DIR/honcho.pid")" 2>/dev/null || true

# Brief readiness smoke so a silent crash is visible immediately.
sleep 4
ok=1
for url in \
  "http://127.0.0.1:8000/v1/status" \
  "http://127.0.0.1:5173/" \
  "http://127.0.0.1:7880/" \
  "http://127.0.0.1:8200/healthz" \
  "http://127.0.0.1:8300/healthz"
do
  if ! curl -sf -m 2 "$url" >/dev/null; then
    echo "WARN: not ready yet: $url" >&2
    ok=0
  fi
done
if [[ "$ok" -ne 1 ]]; then
  echo "WARN: some native endpoints not ready — check $STATE_DIR/honcho.log" >&2
  if grep -qE 'address already in use|Application startup failed' "$STATE_DIR/honcho.log" 2>/dev/null; then
    echo "ERROR: a Procfile process failed; honcho likely stopped the voice stack." >&2
    tail -40 "$STATE_DIR/honcho.log" >&2 || true
    exit 1
  fi
fi

echo ""
echo "Demo stack starting."
echo "  API:        http://127.0.0.1:8000"
echo "  Web:        http://127.0.0.1:5173"
echo "  LiveKit:    ws://127.0.0.1:7880"
echo "  ASR:        http://127.0.0.1:8200/healthz"
echo "  TTS:        http://127.0.0.1:8300/healthz"
echo "  Biz:        http://127.0.0.1:8100  (in Procfile)"
echo "  Review:     http://127.0.0.1:8501  (make review)"
echo "  Worker metrics: http://127.0.0.1:${CALLSCOPE_METRICS_PORT}/metrics"
echo "  Prometheus: http://127.0.0.1:9090"
echo "  Grafana:    http://127.0.0.1:3000  (admin / \$GRAFANA_ADMIN_PASSWORD)"
echo "  Showcase:   file://$ROOT/docs/showcase/index.html"
echo "  Runbook:    docs/runbooks/demo.md"
echo "  Logs:       $STATE_DIR/honcho.log"
echo ""
echo "Hermes is NOT auto-started (install + infra/hermes profile). Optional: hermes gateway run"
echo "Stop with: make demo-stop"
