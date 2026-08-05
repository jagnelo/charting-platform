# ──────────────────────────────────────────────────────────────────────────────
# Charting Platform — Developer Makefile
#
# Development (no Docker rebuilds for code changes):
#   make dev-install     One-time setup of all dependencies
#   make dev-infra       Start Postgres + Redis containers only
#   make dev             Start backend + worker + frontend with hot-reload
#
# Testing:
#   make test            Unit + integration + frontend unit (~40s)
#   make test-unit       Backend unit tests only (no containers, ~5s)
#   make test-int        Backend integration tests (testcontainers, ~30s)
#   make test-fe         Frontend Vitest tests (~3s)
#   make test-e2e        Playwright E2E headless against a running full stack
#   make test-platform   Full validation: tests + Docker stack + headless E2E
#
# Other:
#   make migrate         Apply pending Alembic migrations
#   make lint            Ruff + tsc
#   make coverage        Open HTML coverage reports
#   make clean           Remove build artefacts
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: \
  dev dev-install dev-infra dev-infra-stop dev-backend dev-worker dev-frontend \
  test test-unit test-int test-backend test-fe test-e2e-install test-e2e test-e2e-headed \
  test-stack-up test-stack-down test-platform test-all test-backend-coverage \
  lint lint-backend lint-frontend format \
  migrate migrate-new migrate-down \
  coverage clean ci

# ENV_FILE is passed to every local backend command so pydantic-settings
# loads backend/.env.dev instead of looking for a .env file.
BACKEND_ENV := ENV_FILE=.env.dev
# Read LOG_LEVEL from the dev env file so uvicorn's --log-level matches it.
BACKEND_LOG_LEVEL := $(shell grep -E '^LOG_LEVEL=' backend/.env.dev 2>/dev/null | cut -d= -f2 | tr '[:upper:]' '[:lower:]')
BACKEND_LOG_LEVEL := $(if $(BACKEND_LOG_LEVEL),$(BACKEND_LOG_LEVEL),info)
DEV_STACK_HELPER := ./scripts/dev-stack.sh
DEV_COMPOSE_PROJECT := $(shell $(DEV_STACK_HELPER) project-name dev)
STACK_COMPOSE_PROJECT := $(shell $(DEV_STACK_HELPER) project-name stack)
DEV_BRANCH_NAME := $(shell $(DEV_STACK_HELPER) branch-name)

# ── Dev environment ────────────────────────────────────────────────────────────

dev-install:
	@echo "▶  Checking for uv..."
	@command -v uv >/dev/null 2>&1 || \
	  (echo "uv not found — installing..." && curl -LsSf https://astral.sh/uv/install.sh | sh && \
	   echo "Restart your shell or run: source ~/.cargo/env")
	@echo "▶  Installing backend dependencies..."
	cd backend && uv sync --dev
	@echo "▶  Installing frontend dependencies..."
	cd frontend && npm install
	@echo ""
	@echo "✅  All done. Now run:"
	@echo "    make dev-infra   # start Postgres + Redis"
	@echo "    make dev         # start everything with hot-reload"

dev-infra:
	@echo "▶  Starting branch-scoped Postgres + Redis..."
	@echo "   Branch  →  $(DEV_BRANCH_NAME)"
	@echo "   Project →  $(DEV_COMPOSE_PROJECT)"
	@$(DEV_STACK_HELPER) stop-others docker-compose.dev.yml dev
	COMPOSE_PROJECT_NAME=$(DEV_COMPOSE_PROJECT) docker compose -f docker-compose.dev.yml up -d
	@echo "▶  Waiting for Postgres to be ready..."
	@for i in $$(seq 1 30); do \
	  COMPOSE_PROJECT_NAME=$(DEV_COMPOSE_PROJECT) docker compose -f docker-compose.dev.yml exec postgres pg_isready -U postgres -q 2>/dev/null && break; \
	  sleep 1; \
	done
	@echo "▶  Applying migrations..."
	cd backend && $(BACKEND_ENV) uv run alembic upgrade head
	@echo "✅  Infrastructure ready — Postgres :5432, Redis :6379"
	@echo "   Data is isolated under Docker project $(DEV_COMPOSE_PROJECT)"

dev-infra-stop:
	@echo "▶  Stopping branch-scoped dev stack $(DEV_COMPOSE_PROJECT)"
	COMPOSE_PROJECT_NAME=$(DEV_COMPOSE_PROJECT) docker compose -f docker-compose.dev.yml down

dev-backend:
	cd backend && $(BACKEND_ENV) uv run uvicorn app.main:app \
	  --host 0.0.0.0 --port 8000 --reload --reload-dir app --log-level $(BACKEND_LOG_LEVEL)

dev-worker:
	cd backend && $(BACKEND_ENV) uv run watchfiles "arq app.tasks.worker.WorkerSettings" app

dev-frontend:
	cd frontend && npm run dev

dev:
	@echo "▶  Starting dev environment..."
	@echo "   Backend  →  http://localhost:8000"
	@echo "   API docs →  http://localhost:8000/docs"
	@echo "   Frontend →  http://localhost:5173"
	@echo ""
	./dev.sh all

# ── Migrations ─────────────────────────────────────────────────────────────────

migrate:
	cd backend && $(BACKEND_ENV) uv run alembic upgrade head

migrate-new:
	@read -p "Migration description: " name; \
	cd backend && $(BACKEND_ENV) uv run alembic revision --autogenerate -m "$$name"

migrate-down:
	cd backend && $(BACKEND_ENV) uv run alembic downgrade -1

# ── Tests ──────────────────────────────────────────────────────────────────────

test-unit:
	@echo "▶  Backend unit tests (no containers)..."
	cd backend && $(BACKEND_ENV) uv run pytest tests/unit \
	  --cov=app --cov-report=term-missing \
	  --no-header -q

test-int:
	@echo "▶  Backend integration tests (testcontainers)..."
	cd backend && $(BACKEND_ENV) uv run pytest tests/integration \
	  --cov=app --cov-report=term-missing --cov-report=html:coverage_html \
	  --no-header -q

test-backend: test-unit test-int

# Full backend coverage gate: combine the no-container unit suite with the
# Docker-backed integration suite so coverage reflects the API/runtime paths
# that are intentionally exercised only against PostgreSQL/Redis.
test-backend-coverage:
	@echo "▶  Combined backend unit + integration coverage (Docker required)..."
	cd backend && $(BACKEND_ENV) uv run pytest tests/unit tests/integration \
	  --cov=app --cov-report=term-missing --cov-report=html:coverage_html \
	  --cov-report=xml:coverage-combined.xml --cov-fail-under=75 \
	  --no-header -q

test-fe:
	@echo "▶  Frontend unit tests (Vitest)..."
	cd frontend && npx vitest run --coverage

test-e2e-install:
	@echo "▶  Ensuring Playwright Chromium is installed..."
	cd frontend && npx playwright install chromium

test-e2e: test-e2e-install
	@echo "▶  E2E tests (Playwright headless — stack must be running on :80)..."
	cd frontend && STACK_URL=$${STACK_URL:-http://localhost} npx playwright test

test-e2e-headed: test-e2e-install
	@echo "▶  E2E tests (Playwright headed)..."
	cd frontend && STACK_URL=$${STACK_URL:-http://localhost} npx playwright test --headed

test-stack-up:
	@echo "▶  Starting branch-scoped full application stack for browser validation..."
	@echo "   Branch  →  $(DEV_BRANCH_NAME)"
	@echo "   Project →  $(STACK_COMPOSE_PROJECT)"
	@$(DEV_STACK_HELPER) stop-others docker-compose.yml stack
	E2E_SEED_INSTRUMENTS=true COMPOSE_BAKE=true COMPOSE_PROJECT_NAME=$(STACK_COMPOSE_PROJECT) docker compose up -d --build --wait
	@echo "▶  Applying migrations to the running stack..."
	$(MAKE) migrate

test-stack-down:
	@echo "▶  Stopping branch-scoped full application stack $(STACK_COMPOSE_PROJECT)..."
	COMPOSE_PROJECT_NAME=$(STACK_COMPOSE_PROJECT) docker compose down -v

test: test-unit test-int test-fe
	@echo ""
	@echo "✅  All tests passed. Run 'make test-e2e' for E2E browser tests."

test-platform:
	@echo "▶  Full platform validation (backend + frontend + headless E2E)..."
	@set -e; \
	trap '$(MAKE) test-stack-down' EXIT; \
	$(MAKE) test; \
	$(MAKE) test-stack-up; \
	$(MAKE) test-e2e

test-all: test-platform

# ── Linting & formatting ───────────────────────────────────────────────────────

lint-backend:
	cd backend && uv run ruff check app tests
	cd backend && uv run ruff format --check app tests

lint-frontend:
	cd frontend && npx tsc --noEmit

lint: lint-backend lint-frontend

format:
	cd backend && uv run ruff check --fix app tests
	cd backend && uv run ruff format app tests

# ── Coverage reports ───────────────────────────────────────────────────────────

coverage:
	@open backend/coverage_html/index.html 2>/dev/null || \
	  xdg-open backend/coverage_html/index.html 2>/dev/null || \
	  echo "Open: backend/coverage_html/index.html"
	@open frontend/coverage/index.html 2>/dev/null || \
	  xdg-open frontend/coverage/index.html 2>/dev/null || \
	  echo "Open: frontend/coverage/index.html"

# ── CI ─────────────────────────────────────────────────────────────────────────

ci:
	cd backend && uv sync --dev
	cd frontend && npm ci
	$(MAKE) test
	cd frontend && npx playwright install --with-deps chromium
	COMPOSE_BAKE=true COMPOSE_PROJECT_NAME=$(STACK_COMPOSE_PROJECT) docker compose up -d --build --wait
	$(MAKE) test-e2e
	COMPOSE_PROJECT_NAME=$(STACK_COMPOSE_PROJECT) docker compose down -v

# ── Cleanup ────────────────────────────────────────────────────────────────────

clean:
	rm -rf backend/.pytest_cache backend/coverage_html backend/coverage.xml backend/.coverage
	rm -rf frontend/coverage frontend/playwright-report frontend/test-results
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
