#!/usr/bin/env bash
# PM Studio — one-command Contabo VPS setup
# Run from project root after git clone:
#   bash scripts/setup-contabo.sh
#
# Optional env overrides:
#   PUBLIC_HOST=185.185.80.147 PUBLIC_PORT=8090 bash scripts/setup-contabo.sh
#   bash scripts/setup-contabo.sh --with-nginx   # also installs nginx site (needs sudo)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE_FILE="docker-compose.contabo.yml"
PUBLIC_HOST="${PUBLIC_HOST:-185.185.80.147}"
PUBLIC_PORT="${PUBLIC_PORT:-8090}"
PUBLIC_URL="${PUBLIC_URL:-http://${PUBLIC_HOST}:${PUBLIC_PORT}}"
DB_PASSWORD="${DB_PASSWORD:-prod_secure_password_123}"
WITH_NGINX=false

for arg in "$@"; do
  case "$arg" in
    --with-nginx) WITH_NGINX=true ;;
    -h|--help)
      echo "Usage: bash scripts/setup-contabo.sh [--with-nginx]"
      echo "  PUBLIC_HOST, PUBLIC_PORT, PUBLIC_URL, DB_PASSWORD — optional env vars"
      exit 0
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found. Install Docker first."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose v2 not found."
  exit 1
fi

echo "=============================================="
echo " PM Studio — Contabo setup"
echo " Public URL : $PUBLIC_URL"
echo " Compose    : $COMPOSE_FILE"
echo "=============================================="

# --- Generate JWT secret ---
if command -v openssl >/dev/null 2>&1; then
  JWT_SECRET="$(openssl rand -hex 32)"
else
  JWT_SECRET="pm-studio-$(date +%s)-change-me-in-production-min-32-chars"
fi

# --- Generate .env from template ---
if [[ ! -f deploy/contabo/env.template ]]; then
  echo "ERROR: deploy/contabo/env.template not found."
  exit 1
fi

sed \
  -e "s|__DB_PASSWORD__|${DB_PASSWORD}|g" \
  -e "s|__JWT_SECRET__|${JWT_SECRET}|g" \
  -e "s|__PUBLIC_URL__|${PUBLIC_URL}|g" \
  deploy/contabo/env.template > .env

echo "✓ Created .env (AI keys empty — add later in Admin → AI config)"

export DB_PASSWORD
export NEXT_PUBLIC_API_URL="${PUBLIC_URL}/api/v1"

# --- Build and start ---
echo "→ Building and starting containers (first run may take 10–15 min)..."
docker compose -f "$COMPOSE_FILE" up -d --build

echo "→ Waiting for PostgreSQL..."
for i in $(seq 1 30); do
  if docker compose -f "$COMPOSE_FILE" exec -T postgres pg_isready -U pmstudio >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

echo "→ Running database migrations..."
docker compose -f "$COMPOSE_FILE" exec -T backend alembic upgrade head

echo "→ Health check..."
sleep 3
if curl -sf "http://127.0.0.1:8005/health" >/dev/null; then
  echo "✓ Backend healthy"
else
  echo "⚠ Backend not responding yet — check: docker compose -f $COMPOSE_FILE logs backend"
fi

docker compose -f "$COMPOSE_FILE" ps

# --- Optional nginx ---
if [[ "$WITH_NGINX" == true ]]; then
  echo "→ Installing nginx site..."
  sudo cp deploy/contabo/nginx-pm-studio-8090.conf /etc/nginx/sites-available/pm-studio-8090
  sudo ln -sf /etc/nginx/sites-available/pm-studio-8090 /etc/nginx/sites-enabled/pm-studio-8090
  sudo nginx -t
  sudo systemctl reload nginx
  sudo ufw allow 8090/tcp 2>/dev/null || true
  echo "✓ nginx configured on port $PUBLIC_PORT"
fi

echo ""
echo "=============================================="
echo " DONE"
echo "=============================================="
echo ""
echo " Open in browser: $PUBLIC_URL"
echo " Register first user at login screen."
echo " Add AI keys: Studio → Admin → AI config"
echo ""
if [[ "$WITH_NGINX" != true ]]; then
  echo " Next — nginx (one time):"
  echo "   sudo cp deploy/contabo/nginx-pm-studio-8090.conf /etc/nginx/sites-available/pm-studio-8090"
  echo "   sudo ln -sf /etc/nginx/sites-available/pm-studio-8090 /etc/nginx/sites-enabled/"
  echo "   sudo nginx -t && sudo systemctl reload nginx"
  echo "   sudo ufw allow 8090/tcp"
  echo ""
  echo " Or re-run: bash scripts/setup-contabo.sh --with-nginx"
fi
echo " Logs: docker compose -f $COMPOSE_FILE logs -f celery-worker"
echo "=============================================="
