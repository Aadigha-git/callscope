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

# Best-effort: stop leftover named processes from a crashed demo / solo restarts.
# (Honcho SIGTERMs siblings when any Procfile process dies; orphans often remain.)
pkill -f "livekit-server --dev" 2>/dev/null || true
pkill -f "python -m apps.api" 2>/dev/null || true
pkill -f "python -m apps.biz" 2>/dev/null || true
pkill -f "python -m servers.asr" 2>/dev/null || true
pkill -f "python -m servers.tts" 2>/dev/null || true
pkill -f "python -m apps.worker" 2>/dev/null || true
# Vite may have moved off 5173 if the port was busy; match by apps/web path.
pkill -f "apps/web/node_modules/.bin/vite" 2>/dev/null || true
pkill -f "vite --host 127.0.0.1 --port 5173" 2>/dev/null || true

# Free demo ports if something else still holds them.
for port in 7880 8000 8100 8200 8300 5173 9100; do
  pids="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    echo "==> Freeing :$port (pids: $pids)"
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

echo "==> Compose down"
docker compose -f docker-compose.local.yml down

echo "Demo stopped."
