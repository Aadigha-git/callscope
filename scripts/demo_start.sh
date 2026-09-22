#!/usr/bin/env bash
# Start Compose data plane + native Procfile processes (T-M1-11).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STATE_DIR="${CALLSCOPE_DEMO_STATE:-$ROOT/.demo}"
mkdir -p "$STATE_DIR"

echo "==> Compose data plane (Postgres, MinIO, Prometheus, Grafana)"
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

if [[ ! -d apps/web/node_modules ]]; then
  echo "==> npm install (apps/web)"
  (cd apps/web && npm install)
fi

export CALLSCOPE_METRICS_PORT="${CALLSCOPE_METRICS_PORT:-9100}"
export CALLSCOPE_ASR_BACKEND="${CALLSCOPE_ASR_BACKEND:-fake}"
export CALLSCOPE_TTS_BACKEND="${CALLSCOPE_TTS_BACKEND:-fake}"

echo "==> Native processes via honcho (Procfile)"
# Prefer uv-run honcho so the venv binary is used.
nohup uv run honcho start -f Procfile >"$STATE_DIR/honcho.log" 2>&1 &
echo $! >"$STATE_DIR/honcho.pid"

echo ""
echo "Demo stack starting."
echo "  API:        http://127.0.0.1:8000"
echo "  Web:        http://127.0.0.1:5173"
echo "  LiveKit:    ws://127.0.0.1:7880"
echo "  ASR:        http://127.0.0.1:8200/healthz"
echo "  TTS:        http://127.0.0.1:8300/healthz"
echo "  Biz:        http://127.0.0.1:8100  (if started: make biz)"
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
