# Deployment

## Standard deployment — Docker Compose on a NAS/home server

This is the intended production setup: five containers, all managed by Docker Compose, data persisted in named volumes.

### Prerequisites

- Docker Engine 24+
- Docker Compose v2 (`docker compose`, not `docker-compose`)
- 2 GB RAM available for the stack
- Ports 4173 (frontend) and 8000 (backend API) reachable from your LAN

### First-time setup

```bash
# 1. Copy and fill in the environment file
cp .env.example .env
# Required: set SECRET_KEY
echo "SECRET_KEY=$(openssl rand -hex 32)" >> .env

# 2. Start all containers
docker compose up -d

# 3. Run DB migrations (only needed on first start or after schema changes)
docker compose exec backend alembic upgrade head

# 4. Open the app
open http://your-nas-ip
```

### Subsequent starts

```bash
docker compose up -d          # start/resume
docker compose down           # stop (data preserved in volumes)
docker compose down -v        # stop AND delete all data (destructive)
```

### Updating

```bash
git pull
docker compose build --no-cache
docker compose up -d
docker compose exec backend alembic upgrade head   # apply any new migrations
```

---

## HTTPS with nginx reverse proxy

If you expose the app to the internet (or just want HTTPS on your LAN), put nginx in front. This example uses Certbot for a free Let's Encrypt certificate.

### nginx config (`/etc/nginx/sites-available/charts`)

```nginx
server {
    listen 80;
    server_name charts.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name charts.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/charts.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/charts.yourdomain.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # Frontend SPA
    location / {
        proxy_pass         http://localhost:4173;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
    }

    # Backend API
    location /api/ {
        proxy_pass         http://localhost:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
    }

    # WebSocket (must use upgrade headers)
    location /api/v1/alerts/ws {
        proxy_pass         http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_read_timeout 3600s;
    }
}
```

```bash
# Install Certbot and get a certificate
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d charts.yourdomain.com

# Enable the site
sudo ln -s /etc/nginx/sites-available/charts /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

Update `CORS_ORIGINS` in `.env` to include your HTTPS domain:
```
CORS_ORIGINS=["https://charts.yourdomain.com"]
```

---

## Backup and restore

### What needs to be backed up

All application data lives in two Docker named volumes:

| Volume | Contents |
|---|---|
| `charting-platform_postgres_data` | All OHLCV bars, user data, drawings, alerts, screeners |
| `charting-platform_redis_data` | Task queue state (safe to lose — tasks simply re-queue) |

Only the Postgres volume is essential. Redis can always be recreated.

### Backup

```bash
# Stop the stack to ensure a consistent snapshot (optional but recommended)
docker compose stop

# Dump the entire Postgres database
docker compose exec postgres pg_dumpall -U postgres > backup_$(date +%Y%m%d_%H%M%S).sql

# Or use pg_dump for a single database
docker compose exec postgres pg_dump -U postgres chartingdb > chartingdb_$(date +%Y%m%d).sql

# Resume
docker compose start
```

### Restore

```bash
# Fresh environment — containers must be running with an empty DB
docker compose up -d
docker compose exec backend alembic upgrade head

# Restore from dump
cat chartingdb_20240301.sql | docker compose exec -T postgres psql -U postgres chartingdb
```

### Automated daily backup (cron)

Add to your crontab (`crontab -e`):
```cron
0 3 * * * cd /path/to/charting-platform && docker compose exec postgres pg_dump -U postgres chartingdb > /backups/chartingdb_$(date +\%Y\%m\%d).sql 2>&1
# Keep 30 days of backups
0 4 * * * find /backups -name "chartingdb_*.sql" -mtime +30 -delete
```

---

## Environment variables reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | **Yes** | — | 64-char hex string for JWT signing. Generate: `openssl rand -hex 32` |
| `DATABASE_URL` | No | Set by Compose | PostgreSQL connection string |
| `REDIS_URL` | No | Set by Compose | Redis connection string |
| `CORS_ORIGINS` | No | `["http://localhost:4173"]` | JSON array of allowed origins |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `60` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `30` | Refresh token lifetime |
| `ALERT_POLL_INTERVAL` | No | `60` | Seconds between alert evaluation ticks |
| `ONESIGNAL_APP_ID` | No | — | OneSignal app ID for push notifications |
| `ONESIGNAL_REST_API_KEY` | No | — | OneSignal REST API key |
| `MAX_SCREENER_INSTRUMENTS` | No | `500` | Cap on instruments scanned per screener run |
