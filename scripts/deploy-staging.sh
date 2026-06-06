#!/usr/bin/env bash
# PM Studio staging deployment helper
set -euo pipefail

echo "Building and starting PM Studio via Docker Compose..."
docker compose build
docker compose up -d

echo "Running database migrations..."
docker compose exec backend alembic upgrade head

echo "Deployment complete. Backend: :8000  Frontend: :3000"
echo "Configure Nginx reverse proxy + Certbot SSL on your VPS separately."
