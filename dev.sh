#!/usr/bin/env bash
# dev.sh — Start the full development environment
#
# Opens three processes in parallel:
#   1. FastAPI backend   (hot-reload via uvicorn --reload)
#   2. ARQ worker        (restarts on code change)
#   3. Vue frontend      (Vite HMR)
#
# Prerequisites (run once):  make dev-install
# Infrastructure must be up: make dev-infra
#
# Usage:
#   ./dev.sh              # start everything
#   ./dev.sh backend      # backend only
#   ./dev.sh frontend     # frontend only
#   ./dev.sh worker       # ARQ worker only

set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
DEV_STACK_HELPER="$ROOT/scripts/dev-stack.sh"
RUNTIME_HELPER="$ROOT/scripts/worktree-runtime.py"
RUNTIME_ENV_FILE="$(python3 "$RUNTIME_HELPER" env-file)"
set -a
# shellcheck disable=SC1090
. "$RUNTIME_ENV_FILE"
set +a
DEV_COMPOSE_PROJECT="$DEV_COMPOSE_PROJECT"
DEV_BRANCH_NAME="$WORKTREE_BRANCH"

# ── Colour helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'

log()  { echo -e "${CYAN}[dev]${NC} $*"; }
ok()   { echo -e "${GREEN}[dev]${NC} $*"; }
warn() { echo -e "${YELLOW}[dev]${NC} $*"; }
err()  { echo -e "${RED}[dev]${NC} $*" >&2; }

# ── Prerequisite checks ────────────────────────────────────────────────────────
check_prerequisites() {
    if ! command -v uv &>/dev/null; then
        err "uv not found. Install it: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
    if ! command -v node &>/dev/null; then
        err "node not found. Install Node.js 20+: https://nodejs.org"
        exit 1
    fi
    if ! command -v docker &>/dev/null; then
        err "docker not found. Install Docker Desktop."
        exit 1
    fi
}

# ── Infrastructure ─────────────────────────────────────────────────────────────
start_infra() {
    log "Starting branch-scoped Postgres + Redis..."
    log "Branch: $DEV_BRANCH_NAME"
    log "Docker project: $DEV_COMPOSE_PROJECT"
    COMPOSE_PROJECT_NAME="$DEV_COMPOSE_PROJECT" docker compose -f "$ROOT/docker-compose.dev.yml" \
        -p "$DEV_COMPOSE_PROJECT" up -d

    log "Waiting for Postgres to be ready..."
    for i in $(seq 1 30); do
        COMPOSE_PROJECT_NAME="$DEV_COMPOSE_PROJECT" docker compose -f "$ROOT/docker-compose.dev.yml" \
            -p "$DEV_COMPOSE_PROJECT" exec postgres \
            pg_isready -U postgres -q 2>/dev/null && break
        sleep 1
    done
    ok "Postgres ready"

    log "Running DB migrations..."
    cd "$BACKEND" && ENV_FILE=.env.dev uv run alembic upgrade head
    ok "Migrations applied"
    ok "Branch-isolated dev data is attached to Docker project $DEV_COMPOSE_PROJECT"
}

# ── Process launchers ──────────────────────────────────────────────────────────
run_backend() {
    log "Starting FastAPI backend on :$DEV_BACKEND_PORT (hot-reload)..."
    cd "$BACKEND" && ENV_FILE=.env.dev uv run uvicorn app.main:app \
        --host 0.0.0.0 \
        --port "$DEV_BACKEND_PORT" \
        --reload \
        --reload-dir app \
        --log-level debug
}

run_worker() {
    log "Starting ARQ worker..."
    cd "$BACKEND" && ENV_FILE=.env.dev uv run watchfiles \
        "arq app.tasks.worker.WorkerSettings" app
}

run_frontend() {
    log "Starting Vite dev server on :$VITE_PORT (HMR)..."
    cd "$FRONTEND" && VITE_PORT="$VITE_PORT" VITE_API_PROXY_TARGET="$VITE_API_PROXY_TARGET" npm run dev
}

# ── Main ───────────────────────────────────────────────────────────────────────
check_prerequisites

MODE="${1:-all}"

case "$MODE" in
    backend)
        start_infra
        run_backend
        ;;
    worker)
        run_worker
        ;;
    frontend)
        run_frontend
        ;;
    infra)
        start_infra
        ;;
    all)
        start_infra

        cleanup() {
            echo ""
            log "Shutting down dev processes..."
            kill 0
        }
        trap cleanup SIGINT SIGTERM

        ok "Starting all dev processes. Press Ctrl+C to stop."
        echo ""
        echo "  Backend  →  http://localhost:$DEV_BACKEND_PORT"
        echo "  API docs →  http://localhost:$DEV_BACKEND_PORT/docs"
        echo "  Frontend →  http://localhost:$VITE_PORT"
        echo ""

        run_backend  &
        sleep 2
        run_worker   &
        run_frontend &

        wait -n 2>/dev/null || wait
        ;;
    *)
        err "Unknown mode: $MODE"
        echo "Usage: ./dev.sh [all|backend|worker|frontend|infra]"
        exit 1
        ;;
esac
