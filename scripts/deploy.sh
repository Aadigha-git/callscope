#!/usr/bin/env bash
# Usage: scripts/deploy.sh <staging|demo> <user@host>
# Syncs the compose files + config to the node and restarts services. Secrets live ON the node
# (/opt/callscope/.env, mode 600) and are never copied from CI.
set -euo pipefail
TARGET="${1:?target}"; HOST="${2:?user@host}"
COMPOSE="docker-compose.${TARGET}.yml"
[ -f "$COMPOSE" ] || { echo "missing $COMPOSE (created in task T-M1-11)"; exit 1; }
rsync -az --delete -e "ssh -i ~/.ssh/id_deploy" \
  --include="$COMPOSE" --include="infra/***" --include="db/***" --exclude="*" \
  ./ "$HOST:/opt/callscope/"
ssh -i ~/.ssh/id_deploy "$HOST" "cd /opt/callscope && docker compose -f $COMPOSE pull && docker compose -f $COMPOSE up -d --remove-orphans && docker compose -f $COMPOSE ps"
