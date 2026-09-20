#!/usr/bin/env bash
# Run ON the Nebius GPU node (or any CUDA host). Safe to re-run.
# Does not install packages without confirmation flags; prints diagnostics by default.
set -euo pipefail

CONFIRM_INSTALL="${CONFIRM_INSTALL:-0}"
OUT_DIR="${OUT_DIR:-.}"

log() { printf '[bootstrap] %s\n' "$*"; }

log "host=$(hostname) user=$(whoami) date=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
log "uname=$(uname -a)"

if command -v nvidia-smi >/dev/null 2>&1; then
  log "nvidia-smi present"
  nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu \
    --format=csv
  nvidia-smi
else
  log "ERROR: nvidia-smi not found — GPU drivers missing"
  exit 1
fi

if command -v docker >/dev/null 2>&1; then
  log "docker=$(docker --version)"
  if docker info >/dev/null 2>&1; then
    log "docker daemon reachable"
  else
    log "WARN: docker installed but daemon not reachable (permissions?)"
  fi
else
  log "docker not installed"
  if [[ "$CONFIRM_INSTALL" == "1" ]]; then
    log "INSTALL: following NVIDIA Container Toolkit docs for this distro"
    # Intentionally not auto-curl|bash; operator follows docs for their OS.
    log "See: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html"
  else
    log "Set CONFIRM_INSTALL=1 after reading NVIDIA container toolkit install guide"
  fi
fi

# nvidia-container-toolkit / runtime check
if command -v nvidia-ctk >/dev/null 2>&1; then
  log "nvidia-ctk=$(nvidia-ctk --version 2>/dev/null || true)"
elif dpkg -l 2>/dev/null | grep -q nvidia-container-toolkit; then
  log "nvidia-container-toolkit package present (dpkg)"
else
  log "WARN: nvidia-container-toolkit not detected"
fi

# Docker GPU smoke (optional)
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  if docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi >/tmp/cs-gpu-docker-smi.txt 2>&1; then
    log "docker --gpus all smoke OK"
    head -20 /tmp/cs-gpu-docker-smi.txt
  else
    log "WARN: docker --gpus all smoke failed (see /tmp/cs-gpu-docker-smi.txt)"
  fi
fi

# Persistent cache mount hint
log "expected model cache mount: /var/lib/callscope/models (or \$CALLSCOPE_MODEL_CACHE)"
if [[ -d /var/lib/callscope/models ]]; then
  df -h /var/lib/callscope/models || true
  du -sh /var/lib/callscope/models 2>/dev/null || true
else
  log "cache dir not present yet — create + mount persistent disk before warm measurements"
fi

log "done"
