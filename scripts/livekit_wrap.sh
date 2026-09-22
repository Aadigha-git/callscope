#!/usr/bin/env bash
# Restart loop for livekit-server — if it exits, bring it back without
# taking down the rest of the honcho Procfile (honcho still dies if the
# wrapper exits, so this must never exit on its own).
set -u
while true; do
  echo "[livekit-wrap] starting livekit-server --dev --bind 127.0.0.1"
  livekit-server --dev --bind 127.0.0.1
  code=$?
  echo "[livekit-wrap] livekit-server exited rc=$code; restarting in 1s"
  sleep 1
done
