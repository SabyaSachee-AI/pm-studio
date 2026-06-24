# PM Studio — Contabo VPS (অটো সেটআপ)

API key `.env`-এ দিতে হবে না — পরে **Studio → Admin → AI config** থেকে দেবেন।

**সব অ্যাপের `cd` গাইড:** `deploy/contabo/VPS-OPS.md`

---

## এক কমান্ডে সব (সবচেয়ে সহজ)

VPS-এ SSH করে:

```bash
ssh sabya@185.185.80.147

cd /opt/apps
git clone https://github.com/SabyaSachee-AI/pm-studio.git pm-studio
cd /opt/apps/pm-studio

bash scripts/setup-contabo.sh --with-nginx
```

**এটাই।** Script নিজে করবে:

- `.env` বানাবে (JWT auto-generate)
- Docker service চালু করবে
- Database migration (`alembic upgrade head`)
- nginx port 8090 সেট করবে

---

## PM Studio — আপডেট (প্রতিবার deploy)

```bash
cd /opt/apps/pm-studio
bash scripts/deploy-contabo.sh
```

অথবা manually:

```bash
cd /opt/apps/pm-studio
git pull origin main
docker compose -f docker-compose.contabo.yml up -d --build backend celery-worker celery-build-worker frontend
docker compose -f docker-compose.contabo.yml exec backend alembic upgrade head
```

**কখনোই** শুধু `docker compose up` চালাবেন না — `-f docker-compose.contabo.yml` লাগবে।

---

## nginx ছাড়া (শুধু Docker)

```bash
cd /opt/apps/pm-studio
bash scripts/setup-contabo.sh
```

তারপর nginx manually:

```bash
cd /opt/apps/pm-studio
sudo cp deploy/contabo/nginx-pm-studio-8090.conf /etc/nginx/sites-available/pm-studio-8090
sudo ln -sf /etc/nginx/sites-available/pm-studio-8090 /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo ufw allow 8090/tcp
```

---

## তিনটি অ্যাপ — ফোল্ডার

| অ্যাপ | `cd` |
|-------|------|
| OLM | `cd /opt/apps/office-letter-management-system` |
| Sabya website | `cd /opt/apps/sabya_website` |
| PM Studio | `cd /opt/apps/pm-studio` |

| URL |
|-----|
| OLM: http://185.185.80.147 |
| Website: http://185.185.80.147:8080 |
| PM Studio: http://185.185.80.147:8090 |

---

## Sabya website — 8080 কাজ করছে না

```bash
cd /opt/apps/pm-studio
bash scripts/diagnose-sabya-website-vps.sh

cd /opt/apps/pm-studio
bash scripts/fix-sabya-website-firewall-vps.sh
```

---

## ব্রাউজার (PM Studio)

```
http://185.185.80.147:8090
```

1. **Register** — প্রথম user বানান (`studio_owner` role)
2. **Admin → AI config** — API key entry করুন
3. Project → Requirement upload → AI test

---

## IP বদলালে

```bash
cd /opt/apps/pm-studio
PUBLIC_HOST=YOUR.IP.HERE PUBLIC_PORT=8090 bash scripts/setup-contabo.sh --with-nginx
```

---

## ফাইলগুলো

| ফাইল | কাজ |
|------|-----|
| `deploy/contabo/VPS-OPS.md` | সব অ্যাপ — `cd` + commands |
| `deploy/contabo/env.template` | `.env` template |
| `docker-compose.contabo.yml` | VPS ports (5435, 6381, 8005, 3010) |
| `scripts/deploy-contabo.sh` | Safe PM Studio deploy |
| `scripts/diagnose-sabya-website-vps.sh` | Website diagnose |
| `scripts/fix-sabya-website-firewall-vps.sh` | Website firewall fix |

---

## সমস্যা (PM Studio)

```bash
cd /opt/apps/pm-studio
docker compose -f docker-compose.contabo.yml ps
docker compose -f docker-compose.contabo.yml logs celery-worker --tail 50
curl http://127.0.0.1:8005/health
```

---

## Windows — DB sync

```powershell
cd F:\knowledgebase\ProjectPreparation\PMS\pm-studio
.\scripts\sync-all-to-contabo.ps1 -Apply -Uploads
```
