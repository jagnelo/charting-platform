# Development Guide

## How the dev setup works

In production, everything runs in Docker (5 containers). In development, only the infrastructure (Postgres + Redis) runs in Docker. The backend and frontend run directly on your machine so you get:

- **Instant hot-reload** — save a `.vue` or `.ts` file → Vite updates the browser in <100ms with no page reload (HMR). Save a `.py` file → uvicorn restarts in ~1s.
- **Real debugger support** — attach a debugger to the locally-running Python process directly (no exec into containers).
- **Fast iteration** — no `docker compose build` after every change.

```
Your machine                       Docker
──────────────────────────────     ──────────────────
uvicorn app.main:app --reload  ──► postgres:5432
arq WorkerSettings (watchfiles) 
npm run dev (Vite :5173)           redis:6379
```

---

## First-time setup

### 1. Install uv (Python manager)

[uv](https://docs.astral.sh/uv/) replaces pyenv + pip + venv in one tool. It reads `backend/.python-version` and installs the correct Python automatically.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
# then restart your terminal, or:
source ~/.cargo/env
```

Verify: `uv --version` should print `uv 0.x.x`

### 2. Run one-time setup

```bash
make dev-install
```

This will:
- Install Python 3.12.4 via uv (if not already present)
- Create a virtual environment at `backend/.venv` and install all dependencies
- Run frozen `npm ci` in the frontend
- `ENV_FILE=.env.dev` is passed to all local commands automatically

### 3. Start infrastructure

```bash
make dev-infra
```

Starts Postgres and Redis via `docker-compose.dev.yml`, then runs `alembic upgrade head`.
The allocator derives a persisted resource bundle from the resolved worktree path,
so branch slug collisions still receive different Compose projects, ports,
volumes, networks, URLs, and databases.

When you switch branches and run `make dev-infra`, the tooling starts only the
current worktree's exact project. It never stops another worktree or reclaims a
port by shutting down an unrelated process. Stale registry entries are removed
only after Git no longer lists the worktree and Docker confirms that both exact
managed Compose projects have no running containers; if Docker cannot be
inspected, the entry is left untouched.

That means Alembic history and DB data stay separated by branch, while the local backend/frontend config stays simple.

For concurrent full-stack acceptance projects, the Compose host bindings are overrideable without
changing Docker-internal service URLs:

```bash
POSTGRES_HOST_PORT=55432 BACKEND_HOST_PORT=18000 FRONTEND_HOST_PORT=18080 \
  E2E_SEED_INSTRUMENTS=true E2E_SEED_MARKET_DATA=true \
  docker compose -p charting-acceptance up -d
```

`REDIS_HOST_PORT` is likewise available for the development-only Redis binding.
The defaults are replaced by generated values in `.ai/runtime/*.env`.

Use the supported lifecycle interface from the clean root `master` checkout:

```bash
make worktree-create BRANCH=feat/provider-health
make worktree-list
make worktree-overview
make worktree-status BRANCH=feat/provider-health
make branch-validate
make integrate BRANCH=feat/provider-health
make worktree-close BRANCH=feat/provider-health
make worktree-archive BRANCH=fix/abandoned CONFIRM=fix/abandoned
make integrate-set BRANCHES='docs/a feat/b'
```

If integration pauses on merge conflicts, resolve and stage the candidate's
semantic edits, update `ops/integration-conflicts.md`, then resume it with:

```bash
python3 scripts/integrate.py feat/provider-health --continue --publish
```

If `master` is marked degraded after an independent GitHub replay failure, ordinary
integration remains blocked. A repair branch created directly from that exact degraded
`master` SHA may use the explicit remediation flag; the helper rejects branches with any
other base:

```bash
make integrate BRANCH=fix/master-gate-hardening REMEDIATE_DEGRADED=1
```

Each worktree gets an `ops/workstreams/<branch-slug>/` record with a plan,
handoff, and append-only validation evidence. Closing refuses dirty, unmerged,
or running worktrees.

`make worktree-overview` is the human-facing inventory: it reports branch goal/status,
ahead/behind counts, dirty state, local size, and the exact reason a worktree is or is
not removable. `worktree-archive` is intentionally explicit and only accepts a clean,
stopped, documented blocked/closed branch; it preserves the remote audit branch.

`integrate-set` creates one exact candidate for explicitly named branches, merges each
with a non-fast-forward boundary, runs declared branch tests plus the complete gate, and
publishes one master update. It never adds a branch merely because it is ready.

`make test-stack-up` preserves the normal unseeded market-data default, but accepts
`E2E_SEED_INSTRUMENTS` and `E2E_SEED_MARKET_DATA` from the caller. For deterministic visual
acceptance, use a fresh Compose project/volume with both flags set to `true`; never compare a
seeded render against a persistent canonical-data stack.

### 4. Start everything

```bash
make dev          # starts backend + worker + frontend concurrently
```

Or start them individually in separate terminals for cleaner logs:

```bash
# Terminal 1
make dev-backend    # FastAPI on :8000, restarts on .py changes

# Terminal 2
make dev-worker     # ARQ worker, restarts on .py changes

# Terminal 3
make dev-frontend   # Vite on :5173, HMR on .vue/.ts changes
```

---

## VS Code setup

Install the recommended extensions (`.vscode/extensions.json` is included):
- **ms-python.python** — Python language support
- **ms-python.ruff** — linting and formatting
- **charliermarsh.ruff** — Ruff LSP
- **Vue.volar** — Vue 3 + TypeScript

### Selecting the Python interpreter

After `make dev-install`, the virtual environment is at `backend/.venv`. Tell VS Code to use it:

1. Open the Command Palette (`Cmd+Shift+P`)
2. `Python: Select Interpreter`
3. Choose `backend/.venv/bin/python`

### Launch configuration for debugging

Create `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI backend",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": ["app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
      "cwd": "${workspaceFolder}/backend",
      "env": { "PYTHONPATH": "${workspaceFolder}/backend" },
      "envFile": "${workspaceFolder}/backend/.env.dev",
      "justMyCode": false
    },
    {
      "name": "pytest (current file)",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": ["${file}", "-v"],
      "cwd": "${workspaceFolder}/backend",
      "envFile": "${workspaceFolder}/backend/.env.dev"
    }
  ]
}
```

---

## Connecting to the dev database

```bash
# psql via Docker
COMPOSE_PROJECT_NAME="$(./scripts/dev-stack.sh project-name dev)" docker compose -f docker-compose.dev.yml exec postgres psql -U postgres chartingdb

# Or with a GUI tool — connect to:
#   Host:     localhost
#   Port:     5432
#   Database: chartingdb
#   User:     postgres
#   Password: postgres
```

Useful queries:

```sql
-- How many OHLCV bars do we have?
SELECT timeframe, COUNT(*) FROM ohlcv_bar GROUP BY timeframe ORDER BY timeframe;

-- Active alerts
SELECT u.username, i.symbol, pa.condition, pa.threshold_price, pa.status
FROM price_alert pa
JOIN "user" u ON u.id = pa.user_id
JOIN instrument i ON i.id = pa.instrument_id;

-- Recent screener runs
SELECT s.name, sr.run_at, sr.total_scanned, array_length(sr.matched_instrument_ids, 1) as matched
FROM screener_result sr JOIN screener s ON s.id = sr.screener_id
ORDER BY sr.run_at DESC LIMIT 10;
```

---

## Making schema changes

```bash
# After editing a model file, generate a migration
make migrate-new
# Enter a description: "add_instrument_tags"
# This creates backend/alembic/versions/xxxx_add_instrument_tags.py

# Review the generated migration, then apply it
make migrate

# Undo the last migration
make migrate-down
```

---

## Adding a Python dependency

```bash
# Runtime dependency
cd backend && uv add pandas

# Dev-only dependency (tests, linting)
cd backend && uv add --dev pytest-benchmark

# Then commit the updated pyproject.toml and uv.lock
```

The `uv.lock` file is committed to git. Other developers get identical versions with `uv sync`.

---

## Stopping the dev environment

```bash
# Stop infrastructure (containers) — data preserved in volumes
make dev-infra-stop

# Stop infrastructure AND delete the current branch's dev data (full reset)
COMPOSE_PROJECT_NAME="$(./scripts/dev-stack.sh project-name dev)" docker compose -f docker-compose.dev.yml down -v
```

The backend and frontend stop when you Ctrl+C the `make dev` terminal.
