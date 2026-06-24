#!/usr/bin/env bash
# Diagnose Sabya website (nginx :8080 -> docker :3005) on Contabo VPS.
#
# Run on VPS:
#   cd /opt/apps/pm-studio
#   bash scripts/diagnose-sabya-website-vps.sh

set -euo pipefail

echo "=== Sabya website diagnostic ==="
echo "Run from: cd /opt/apps/pm-studio"
echo ""

echo "Step 1) Docker containers (sabya_website)"
docker ps --filter name=sabya_website --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' || true
echo ""

echo "Step 2) Local upstream (app on 3005)"
if curl -sf -m 5 -o /dev/null -w "   127.0.0.1:3005 -> HTTP %{http_code}\n" http://127.0.0.1:3005/; then
  UPSTREAM_OK=1
else
  echo "   127.0.0.1:3005 -> FAILED (container down or app crash)"
  UPSTREAM_OK=0
fi
echo ""

echo "Step 3) Local nginx (8080)"
if curl -sf -m 5 -o /dev/null -w "   127.0.0.1:8080 -> HTTP %{http_code}\n" http://127.0.0.1:8080/; then
  NGINX_OK=1
else
  echo "   127.0.0.1:8080 -> FAILED (nginx config or upstream)"
  NGINX_OK=0
fi
echo ""

echo "Step 4) Firewall (UFW)"
if command -v ufw >/dev/null 2>&1; then
  sudo ufw status | grep -E '8080|8090|80/tcp' || sudo ufw status
else
  echo "   ufw not installed"
fi
echo ""

echo "Step 5) nginx site config"
if [[ -f /etc/nginx/sites-available/sabya-website-8080 ]]; then
  grep -E 'listen|proxy_pass|server_name' /etc/nginx/sites-available/sabya-website-8080 | sed 's/^/   /'
else
  echo "   MISSING: /etc/nginx/sites-available/sabya-website-8080"
fi
echo ""

echo "Step 6) Recent logs"
if docker ps -q --filter name=sabya_website_web | grep -q .; then
  echo "   --- sabya_website_web (last 20 lines) ---"
  docker logs sabya_website_web --tail 20 2>&1 | sed 's/^/   /'
fi
echo ""

echo "=== Verdict ==="
if [[ "${UPSTREAM_OK:-0}" == 1 && "${NGINX_OK:-0}" == 1 ]]; then
  echo "App + nginx work LOCALLY on the VPS."
  echo "If browser still fails from outside: open port 8080 in UFW + Contabo cloud firewall."
  echo ""
  echo "Permanent fix — run:"
  echo "  cd /opt/apps/pm-studio"
  echo "  bash scripts/fix-sabya-website-firewall-vps.sh"
  echo ""
  echo "Or manually:"
  echo "  cd /opt/apps/sabya_website"
  echo "  sudo ufw allow 8080/tcp comment 'Sabya website'"
  echo "  sudo ufw reload"
  echo "  # Contabo panel -> Firewall -> allow TCP 8080"
elif [[ "${UPSTREAM_OK:-0}" == 0 ]]; then
  echo "App container/upstream is broken. Fix docker:"
  echo "  cd /opt/apps/sabya_website"
  echo "  docker compose ps"
  echo "  docker compose logs web --tail 50"
  echo "  docker compose up -d --build"
else
  echo "nginx proxy broken. Fix:"
  echo "  cd /opt/apps/sabya_website"
  echo "  sudo nginx -t"
  echo "  sudo cat /etc/nginx/sites-available/sabya-website-8080"
  echo "  sudo systemctl reload nginx"
fi
