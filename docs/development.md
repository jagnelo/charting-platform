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
make worktree-create BRANCH=feat/provider-health REQUEST='Add provider-health monitoring'
make worktree-list
make worktree-overview
make worktree-status BRANCH=feat/provider-health
make branch-validate
make integrate BRANCH=feat/provider-health
make worktree-close BRANCH=feat/provider-health
make worktree-archive BRANCH=fix/abandoned CONFIRM=fix/abandoned
make worktree-archive-pre-staging BRANCH=fix/old-ci CONFIRM=fix/old-ci REASON='published local duplicate'
make integrate-set BRANCHES='docs/a feat/b'
make staging-status
make promote-staging COMMIT=<full-green-staging-sha> CONFIRM=<same-sha>
```

Ordinary work starts from green `staging`. Integration merges the exact pushed source
SHA into the persistent staging branch and waits for its exhaustive GitHub gate. No
disposable repository copy is created. On conflict, staging is restored unchanged; record
the intended combined behaviour and affected tests in the source workstream, resolve the
conflict on that source branch, push, and retry.

If `staging` is marked degraded after its exhaustive replay fails, ordinary integration
and promotion remain blocked. A repair branch created directly from that exact degraded
staging SHA may use the explicit remediation flag; the helper rejects branches with any
other base:

```bash
make integrate BRANCH=fix/staging-gate REMEDIATE_DEGRADED=1
```

Each worktree gets an `ops/workstreams/<branch-slug>/` record with a plan,
handoff, and append-only validation evidence. Closing refuses dirty, unmerged,
or running worktrees.

`REQUEST` is a durable record of the human request that authorized the work, not
boilerplate. An agent must not create a worktree, modify product code, integrate,
or deploy merely because it found a potential improvement. It first needs an
explicit human request for that topic.

Before selecting validation, the agent must ask the human whether this topic
needs the default `full_integration` gate or is explicitly approved as
`focused_only` documentation/workflow-helper work. A missing decision blocks
integration. `focused_only` is allowed only for changes limited to `docs/`,
`scripts/`, `Makefile`, `AGENTS.md`, and the branch's own workstream record;
it runs diff/workstream validation, Python syntax checks, and declared focused
tests. Any application, dependency, migration, Compose, CI, or test-product
change requires `full_integration`.

When development is complete, green tests mean `ready_for_human_review`, not
permission to merge for product or deployment work. Keep those branches/worktrees available
while the human tries the result and supplies feedback. A standing human authorization may,
however, let agents finish and close CI/CD-only housekeeping end-to-end once its declared
focused checks are green. That exception never covers application behaviour, provider
monitoring, deployment code/target configuration, live-provider calls, or a red/flaky gate.
Product and deployment topics still require an explicit human closure instruction before an
agent records `human_closure_authorization`, changes the workstream status to
`ready_for_integration`, completes the PR-equivalent `closure_summary`, and runs `make integrate`.
Deployment remains a separate explicit human request.

`make worktree-overview` is the human-facing inventory: it reports branch goal/status,
ahead/behind counts, dirty state, local size, and the exact reason a worktree is or is
not removable. `worktree-archive` is intentionally explicit and only accepts a clean,
stopped, documented blocked/closed branch already in staging; it preserves the remote audit
branch. Before staging is bootstrapped, `worktree-archive-pre-staging` is the separate storage
housekeeping path for a clean local duplicate whose exact branch tip is already published on
master. It never deletes the remote branch or changes the workstream's semantic status.

`integrate-set` merges only explicitly named, human-closed branches into staging with a
non-fast-forward boundary for each. Branch CI includes its declared tests; the resulting
staging SHA receives the exhaustive remote gate. It never infers batch membership.

After the exact staging SHA is green, `promote-staging` fast-forwards master to it and
waits for master's independent exhaustive replay. Normal CI is architecture-neutral and
contains no emulation. RPi architecture validation/building occurs only through an
explicitly requested `rpi-preflight`/`rpi-bundle`/`deploy-rpi` flow using the configured
`RPI_DOCKER_PLATFORM`.

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
