#!/usr/bin/env bash
# PM Studio — safe Contabo deploy (always uses docker-compose.contabo.yml).
# Run on VPS:
#   cd /opt/apps/pm-studio
#   bash scripts/deploy-contabo.sh

set -euo pipefail

ROOT="/opt/apps/pm-studio"
COMPOSE_FILE="docker-compose.contabo.yml"

cd "$ROOT"

echo "=== PM Studio deploy (Contabo) ==="
echo "Directory: $(pwd)"
echo ""

echo "Step 1 — git pull"
git pull origin main
echo ""

echo "Step 2 — build & start"
docker compose -f "$COMPOSE_FILE" up -d --build backend celery-worker celery-build-worker frontend
echo ""

echo "Step 3 — migrations"
docker compose -f "$COMPOSE_FILE" exec -T backend alembic upgrade head
echo ""

echo "Step 4 — status"
docker compose -f "$COMPOSE_FILE" ps
echo ""

echo "Step 5 — health"
curl -sf http://127.0.0.1:8005/health && echo ""
curl -s -o /dev/null -w "frontend 3010: %{http_code}\n" http://127.0.0.1:3010
curl -s -o /dev/null -w "nginx 8090: %{http_code}\n" http://127.0.0.1:8090
echo ""
echo "Public URL: http://185.185.80.147:8090"
