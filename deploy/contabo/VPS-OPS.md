# Contabo VPS — all apps (always `cd` first)

**Server:** `185.185.80.147` | **User:** `sabya`

| App | Folder | Public URL |
|-----|--------|------------|
| OLM | `/opt/apps/office-letter-management-system` | http://185.185.80.147 |
| Sabya website | `/opt/apps/sabya_website` | http://185.185.80.147:8080 |
| PM Studio | `/opt/apps/pm-studio` | http://185.185.80.147:8090 |

---

## SSH (every session)

```bash
ssh sabya@185.185.80.147
```

---

## PM Studio — deploy / update

```bash
cd /opt/apps/pm-studio
git pull origin main
docker compose -f docker-compose.contabo.yml up -d --build backend celery-worker celery-build-worker frontend
docker compose -f docker-compose.contabo.yml exec backend alembic upgrade head
docker compose -f docker-compose.contabo.yml ps
curl -s http://127.0.0.1:8005/health
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8090
```

**Never** run plain `docker compose` in this folder — use `-f docker-compose.contabo.yml` only.

---

## OLM — restart / logs

```bash
cd /opt/apps/office-letter-management-system
docker compose ps
docker compose up -d
docker compose logs backend --tail 50
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/health
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000
```

---

## Sabya website — restart / logs

```bash
cd /opt/apps/sabya_website
docker compose ps
docker compose up -d --build
docker compose logs web --tail 50
curl -s -o /dev/null -w "3005=%{http_code}\n" http://127.0.0.1:3005/
curl -s -o /dev/null -w "8080=%{http_code}\n" http://127.0.0.1:8080/
```

---

## Sabya website — port 8080 not loading (firewall fix)

### Step 1 — Diagnose

```bash
cd /opt/apps/pm-studio
bash scripts/diagnose-sabya-website-vps.sh
```

### Step 2 — If local 3005 and 8080 return 200, open firewall

```bash
cd /opt/apps/sabya_website
sudo ufw allow 8080/tcp comment 'Sabya website'
sudo ufw reload
sudo ufw status | grep 8080
```

Also: **Contabo control panel** → VPS → Firewall → allow **TCP 8080**.

### Step 3 — Test from VPS

```bash
cd /opt/apps/sabya_website
curl -s -o /dev/null -w "3005=%{http_code}\n" http://127.0.0.1:3005/
curl -s -o /dev/null -w "8080=%{http_code}\n" http://127.0.0.1:8080/
```

### Step 4 — If app is down, rebuild

```bash
cd /opt/apps/sabya_website
docker compose ps
docker compose logs web --tail 80
docker compose up -d --build
```

### Step 5 — If nginx broken

```bash
cd /opt/apps/sabya_website
sudo nginx -t
sudo cat /etc/nginx/sites-available/sabya-website-8080
sudo systemctl reload nginx
```

---

## PM Studio — diagnose

```bash
cd /opt/apps/pm-studio
docker compose -f docker-compose.contabo.yml ps
docker compose -f docker-compose.contabo.yml logs backend --tail 50
docker compose -f docker-compose.contabo.yml logs celery-worker --tail 50
curl -s http://127.0.0.1:8005/health
```

---

## Windows — sync DB to Contabo

```powershell
cd F:\knowledgebase\ProjectPreparation\PMS\pm-studio
.\scripts\sync-all-to-contabo.ps1
.\scripts\sync-all-to-contabo.ps1 -Apply -Uploads
.\scripts\sync-spelling-to-contabo.ps1
```

---

## Windows — first-time PM Studio setup on VPS

```bash
ssh sabya@185.185.80.147
cd /opt/apps
git clone https://github.com/SabyaSachee-AI/pm-studio.git pm-studio
cd /opt/apps/pm-studio
bash scripts/setup-contabo.sh --with-nginx
```
