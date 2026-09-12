# Deployment

## Manual Raspberry Pi deployment

The RPi path is an explicit target workflow; it is not part of normal branch,
staging, or master CI. GitHub CI remains architecture-neutral and does not use
QEMU. A human must request deployment of one exact, validated master SHA.

Copy `deploy/rpi/rpi.env.example` to ignored `.ai/deploy/rpi.env`, protect it
with mode `0600`, and set `RPI_DOCKER_PLATFORM` after checking `uname -m` on the
Pi. A 32-bit Pi OS normally needs `linux/arm/v7`; a 64-bit Pi OS needs
`linux/arm64`. The preflight rejects a mismatch rather than guessing.

Provision application and provider secrets separately on the target at
`/opt/charting-platform/shared/app.env` (or
`$RPI_DEPLOY_ROOT/shared/app.env`) with mode `0600`. Use the same variable names
as `.env.example`, but copy them through an approved password/secret manager or
a secure operator channel. The deployment intentionally does not pull secrets
from GitHub or from a developer worktree, and release bundles never contain
them. Compose passes provider credentials only to `backend` and `worker`.

The direct live-probe ledger is optional and contains only provider/request/byte
aggregates. If an operator wants those cross-session probe totals visible in
the backend usage endpoint, mount the owner-managed ledger read-only into the
backend and worker containers and set `PROVIDER_LIVE_USAGE_LEDGER` to its
container path. Do not copy credentials or raw provider payloads into that
mount; an unavailable ledger is safe and does not affect routing.

Identical OHLCV refreshes are coordinated by PostgreSQL transaction-scoped
advisory locks when all workers share one database. A deployment whose backend
instances do not share that transaction boundary may opt into the Redis
coordinator with `OHLCV_DISTRIBUTED_LOCK_ENABLED=true`; every participating
backend and worker must point at the same `REDIS_URL`. Set
`OHLCV_DISTRIBUTED_LOCK_TTL_SECONDS` longer than the slowest permitted refresh,
and keep `OHLCV_DISTRIBUTED_LOCK_WAIT_SECONDS` bounded. If Redis cannot acquire
the lock, the refresh fails closed instead of spending provider quota twice.
The lock is a coordination safeguard, not a provider rate limit, and its
settings must be reviewed per deployment.

Tokenized quote polling is opt-in and disabled by default. If the deployment
has reviewed provider entitlements and quota contracts, set
`TOKENIZED_ASSET_REFRESH_ENABLED=true` and a bounded
`TOKENIZED_ASSET_REFRESH_MAX_ASSETS` in the shared `app.env`; the same values
must reach both `backend` and `worker`. Unknown provider quotas remain
non-routable even when this schedule is enabled.

Tokenized corporate-action persistence is separately opt-in. Set
`TOKENIZED_EVENT_REFRESH_ENABLED=true`,
`TOKENIZED_EVENT_REFRESH_MAX_PROVIDERS`, and
`TOKENIZED_EVENT_REFRESH_PAGE_SIZE` only after the provider-specific action
feed terms and quota contracts have been reviewed. These values must also be
present for both `backend` and `worker`; the schedule is otherwise disabled
and does not consume provider quota.

Market-wide IPO, earnings-calendar, and exchange-event persistence is also
opt-in. Set `MARKET_EVENTS_REFRESH_ENABLED=true`,
`MARKET_EVENTS_REFRESH_LOOKAHEAD_DAYS`, and
`MARKET_EVENTS_REFRESH_MAX_PROVIDERS` in the shared `app.env` only after the
provider-specific market-event entitlements and quota contracts have been
reviewed. The values must reach both `backend` and `worker`; the daily worker
refreshes a bounded UTC forward window and records per-provider failures
without discarding successful observations. The default is disabled and no
provider calls occur until explicitly enabled.

Future-listing materialization is a separate backend/worker opt-in. Set
`MARKET_EVENTS_PRELISTING_ENABLED=true` with bounded
`MARKET_EVENTS_PRELISTING_LOOKAHEAD_DAYS` and
`MARKET_EVENTS_PRELISTING_MAX_EVENTS` only after the event evidence and
promotion policy have been reviewed. It creates inactive provisional stock
instruments and quarantines conflicts; it does not alter frontend services or
silently merge ticker-only identities. Keep it disabled until the deployment
has reviewed the provider/legal and universe-reconciliation gates.

EDGAR filing-driven IPO-pipeline scanning is separately opt-in because EDGAR
does not publish a global IPO-calendar endpoint. Set
`MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_ENABLED=true` with bounded
`MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_LOOKBACK_DAYS`,
`MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_MAX_ISSUERS`, and
`MARKET_EVENTS_EDGAR_UNIVERSE_SCAN_MAX_EVENTS_PER_ISSUER`. The worker walks
CIKs already present in the canonical issuer table, persists its cursor in
`market_event_scan_state`, and reports partial cycles; it never claims that a
bounded batch is a complete SEC universe.

If complete SEC issuer-directory coverage is required for filing-driven
candidate scans, use the separate `MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_ENABLED`
flag with bounded `MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_ISSUERS` and
`MARKET_EVENTS_EDGAR_DIRECTORY_SCAN_MAX_EVENTS_PER_ISSUER` values. This worker
pages unique CIKs from the official SEC ticker directory and stores its offset
in scan-state provenance. It is disabled by default and must not be enabled
without reviewing fair-access, candidate-use, and redistribution requirements.

The core market refresh and US venue/lifecycle reconciliation schedules are also
disabled by default. After the corresponding provider entitlements, quota
contracts, and reconciliation completeness have been reviewed, set
`MARKET_DATA_REFRESH_SCHEDULE_ENABLED=true` and/or
`MARKET_UNIVERSE_RECONCILIATION_ENABLED=true` together with a reviewed
`MARKET_UNIVERSE_MISSING_CONFIRMATIONS` value. These controls are passed to
both `backend` and `worker`, never to the research runner, and do not bypass
provider fail-closed routing.

Provider availability monitoring is independently controlled with
`PROVIDER_AVAILABILITY_MONITOR_ENABLED`,
`PROVIDER_AVAILABILITY_LIVE_ENABLED`, and the notification/cooldown/timeout
settings. Keep live probes disabled unless the deployment has explicitly
approved their provider usage impact; monitoring never widens a quota or
entitlement contract.

```bash
make rpi-preflight
make rpi-bundle COMMIT=<full-validated-master-sha>
make deploy-rpi COMMIT=<full-validated-master-sha> CONFIRM=<same-sha>
make rpi-status
```

The bundle command builds/pulls the configured target architecture on the
developer machine and transfers image-only artifacts; the Pi does not build the
application. If a dependency image does not support the selected Pi platform,
the explicit bundle step fails without changing the Pi. Other future local or
cloud targets may use Linux x86-64 without changing normal CI or pretending the
RPi platform is universal.

## Standard deployment — Docker Compose on a NAS/home server

This is the intended production setup: five containers, all managed by Docker Compose, data persisted in named volumes.

All commands below assume you set `COMPOSE_PROJECT_NAME` first. For local branch-scoped workflows, use the repo helper. For a stable long-lived server deployment, replace it with a fixed name such as `charting-prod`.

### Prerequisites

- Docker Engine 24+
- Docker Compose v2 (`docker compose`, not `docker-compose`)
- 2 GB RAM available for the stack
- Ports 4173 (frontend) and 8000 (backend API) reachable from your LAN

### First-time setup

```bash
# Choose the Compose project name for this checkout/session
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$(./scripts/dev-stack.sh project-name stack)}"

# 1. Create the external owner-only environment file. Repository worktree
# setup links the ignored .env path to it; do not commit or copy it into Git.
install -d -m 700 ~/.config/charting-platform
test -e ~/.config/charting-platform/app.env || \
  install -m 600 /dev/null ~/.config/charting-platform/app.env
# Fill it through your password/secret manager, including a generated
# SECRET_KEY and the provider variables required by this deployment.

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

This example assumes the frontend container is published on `4173` instead of `80`, so nginx can own ports `80` and `443` on the host. If you keep the default `80:80` mapping from `docker-compose.yml`, change that published port before using this layout.

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
| `${COMPOSE_PROJECT_NAME}_postgres_data` | All OHLCV bars, user data, drawings, alerts, screeners |
| `${COMPOSE_PROJECT_NAME}_redis_data` | Task queue state (safe to lose — tasks simply re-queue) |

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
0 3 * * * cd /path/to/charting-platform && COMPOSE_PROJECT_NAME=charting-prod docker compose exec postgres pg_dump -U postgres chartingdb > /backups/chartingdb_$(date +\%Y\%m\%d).sql 2>&1
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
| `CORS_ORIGINS` | No | `["http://localhost"]` | JSON array of allowed origins |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `60` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `30` | Refresh token lifetime |
| `ALERT_POLL_INTERVAL` | No | `60` | Seconds between alert evaluation ticks |
| `ONESIGNAL_APP_ID` | No | — | OneSignal app ID for push notifications |
| `ONESIGNAL_REST_API_KEY` | No | — | OneSignal REST API key |
| `MAX_SCREENER_INSTRUMENTS` | No | `500` | Cap on instruments scanned per screener run |
