#!/usr/bin/env bash
# Open firewall port 8080 for Sabya website (permanent external access).
# Run on VPS:
#   cd /opt/apps/pm-studio
#   bash scripts/fix-sabya-website-firewall-vps.sh

set -euo pipefail

echo "=== Fix Sabya website external access (port 8080) ==="
echo ""

echo "Step 1 — Check app upstream (must be from sabya_website folder)"
echo "  cd /opt/apps/sabya_website"
cd /opt/apps/sabya_website
docker compose ps
if curl -sf -m 5 -o /dev/null http://127.0.0.1:3005/; then
  echo "  OK: 127.0.0.1:3005 responds"
else
  echo "  WARN: 127.0.0.1:3005 failed — run:"
  echo "    cd /opt/apps/sabya_website"
  echo "    docker compose up -d --build"
  exit 1
fi
echo ""

echo "Step 2 — Check nginx on 8080"
if curl -sf -m 5 -o /dev/null http://127.0.0.1:8080/; then
  echo "  OK: 127.0.0.1:8080 responds"
else
  echo "  WARN: nginx 8080 failed — run:"
  echo "    sudo nginx -t"
  echo "    sudo systemctl reload nginx"
  exit 1
fi
echo ""

echo "Step 3 — Open UFW port 8080"
if command -v ufw >/dev/null 2>&1; then
  sudo ufw allow 8080/tcp comment 'Sabya website'
  sudo ufw reload
  sudo ufw status | grep 8080 || true
else
  echo "  ufw not installed — skip"
fi
echo ""

echo "Step 4 — Reminder: Contabo cloud firewall"
echo "  Contabo panel -> VPS -> Firewall -> allow TCP 8080 inbound"
echo ""

echo "Step 5 — Test"
echo "  curl -s -o /dev/null -w '8080=%{http_code}\n' http://127.0.0.1:8080/"
curl -s -o /dev/null -w "  local 8080=%{http_code}\n" http://127.0.0.1:8080/
echo ""
echo "Done. Test from browser: http://185.185.80.147:8080/"
