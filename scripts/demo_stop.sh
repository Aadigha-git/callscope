#!/usr/bin/env bash
# Tear down native Procfile processes + Compose data plane.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
STATE_DIR="${CALLSCOPE_DEMO_STATE:-$ROOT/.demo}"

if [[ -f "$STATE_DIR/honcho.pid" ]]; then
  PID="$(cat "$STATE_DIR/honcho.pid")"
  if kill -0 "$PID" 2>/dev/null; then
    echo "==> Stopping honcho pid=$PID (and children)"
    # Honcho is the parent; kill process group if possible.
    kill -TERM "-$PID" 2>/dev/null || kill -TERM "$PID" 2>/dev/null || true
    sleep 1
    kill -KILL "-$PID" 2>/dev/null || kill -KILL "$PID" 2>/dev/null || true
  fi
  rm -f "$STATE_DIR/honcho.pid"
fi

# Best-effort: stop leftover named processes from a crashed demo.
pkill -f "livekit-server --dev" 2>/dev/null || true
pkill -f "python -m apps.api" 2>/dev/null || true
pkill -f "python -m servers.asr" 2>/dev/null || true
pkill -f "python -m servers.tts" 2>/dev/null || true
pkill -f "python -m apps.worker" 2>/dev/null || true

echo "==> Compose down"
docker compose -f docker-compose.local.yml down

echo "Demo stopped."
