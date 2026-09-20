#!/usr/bin/env bash
# Regenerate synthetic probe audio (delegates to spike harness; keep spikes/ out of ruff).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
exec python3 "$ROOT/spikes/T-M0-06/scripts/generate_probe_audio.py"
