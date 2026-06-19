# PM Studio — Contabo VPS (অটো সেটআপ)

API key `.env`-এ দিতে হবে না — পরে **Studio → Admin → AI config** থেকে দেবেন।

---

## এক কমান্ডে সব (সবচেয়ে সহজ)

VPS-এ SSH করে:

```bash
ssh sabya@185.185.80.147

cd /opt/apps
git clone https://github.com/SabyaSachee-AI/pm-studio.git pm-studio
cd pm-studio

bash scripts/setup-contabo.sh --with-nginx
```

**এটাই।** Script নিজে করবে:

- `.env` বানাবে (JWT auto-generate)
- Docker ৫টা service চালু করবে
- Database migration (`alembic upgrade head`)
- nginx port 8090 সেট করবে

---

## nginx ছাড়া (শুধু Docker)

```bash
bash scripts/setup-contabo.sh
```

তারপর nginx manually:

```bash
sudo cp deploy/contabo/nginx-pm-studio-8090.conf /etc/nginx/sites-available/pm-studio-8090
sudo ln -sf /etc/nginx/sites-available/pm-studio-8090 /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo ufw allow 8090/tcp
```

---

## ব্রাউজার

```
http://185.185.80.147:8090
```

1. **Register** — প্রথম user বানান (`studio_owner` role)
2. **Admin → AI config** — API key entry করুন
3. Project → Requirement upload → AI test

---

## IP বদলালে

```bash
PUBLIC_HOST=YOUR.IP.HERE PUBLIC_PORT=8090 bash scripts/setup-contabo.sh --with-nginx
```

---

## ফাইলগুলো

| ফাইল | কাজ |
|------|-----|
| `deploy/contabo/env.template` | `.env` template |
| `docker-compose.contabo.yml` | VPS ports (5435, 6381, 8005, 3010) |
| `deploy/contabo/nginx-pm-studio-8090.conf` | nginx config |
| `scripts/setup-contabo.sh` | অটো setup script |

---

## সমস্যা

```bash
docker compose -f docker-compose.contabo.yml ps
docker compose -f docker-compose.contabo.yml logs celery-worker --tail 50
curl http://127.0.0.1:8005/health
```
