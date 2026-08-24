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
  test-uplot-contract \
  test-visual-policy \
  test-compose-contract \
  test-migration-compatibility test-research-runner-probes test-live-provider-probes \
  branch-tests \
  validate-arm64-images \
  validate-integration validate-focused-integration branch-validate \
  worktree-create worktree-list worktree-status worktree-overview worktree-close worktree-archive worktree-cleanup-report worktree-cleanup-reconcile worktree-cleanup integrate integrate-set \
  rpi-preflight rpi-bundle deploy-rpi rpi-status \
  lint lint-backend lint-frontend format \
  migrate migrate-new migrate-down \
  coverage clean ci

# ENV_FILE is passed to every local backend command so pydantic-settings
# loads backend/.env.dev instead of looking for a .env file.
BACKEND_ENV := ENV_FILE=.env.dev
WORKFLOW_PYTHON := uv run --project backend python
RUNTIME_HELPER := $(WORKFLOW_PYTHON) scripts/worktree-runtime.py
RUNTIME_ENV_FILE := $(shell $(RUNTIME_HELPER) env-file)
RUNTIME_ENV = set -a; . "$(RUNTIME_ENV_FILE)"; set +a;
# Read LOG_LEVEL from the dev env file so uvicorn's --log-level matches it.
BACKEND_LOG_LEVEL := $(shell grep -E '^LOG_LEVEL=' backend/.env.dev 2>/dev/null | cut -d= -f2 | tr '[:upper:]' '[:lower:]')
BACKEND_LOG_LEVEL := $(if $(BACKEND_LOG_LEVEL),$(BACKEND_LOG_LEVEL),info)
DEV_STACK_HELPER := ./scripts/dev-stack.sh
DEV_COMPOSE_PROJECT := $(shell sed -n 's/^DEV_COMPOSE_PROJECT=//p' "$(RUNTIME_ENV_FILE)" | tr -d "'\"")
STACK_COMPOSE_PROJECT := $(shell sed -n 's/^STACK_COMPOSE_PROJECT=//p' "$(RUNTIME_ENV_FILE)" | tr -d "'\"")
DEV_BRANCH_NAME := $(shell sed -n 's/^WORKTREE_BRANCH=//p' "$(RUNTIME_ENV_FILE)" | tr -d "'\"")

# ── Dev environment ────────────────────────────────────────────────────────────

dev-install:
	@echo "▶  Checking for uv..."
	@command -v uv >/dev/null 2>&1 || \
	  (echo "uv not found — installing..." && curl -LsSf https://astral.sh/uv/install.sh | sh && \
	   echo "Restart your shell or run: source ~/.cargo/env")
	@echo "▶  Installing backend dependencies..."
	cd backend && uv sync --frozen --dev
	@echo "▶  Installing frontend dependencies..."
	cd frontend && npm ci
	@echo ""
	@echo "✅  All done. Now run:"
	@echo "    make dev-infra   # start Postgres + Redis"
	@echo "    make dev         # start everything with hot-reload"

dev-infra:
	@$(RUNTIME_ENV)
	@echo "▶  Starting branch-scoped Postgres + Redis..."
	@echo "   Branch  →  $(DEV_BRANCH_NAME)"
	@echo "   Project →  $(DEV_COMPOSE_PROJECT)"
	$(RUNTIME_ENV) COMPOSE_PROJECT_NAME=$$DEV_COMPOSE_PROJECT docker compose -f docker-compose.dev.yml up -d
	@echo "▶  Waiting for Postgres to be ready..."
	@for i in $$(seq 1 30); do \
	  $(RUNTIME_ENV) COMPOSE_PROJECT_NAME=$$DEV_COMPOSE_PROJECT docker compose -f docker-compose.dev.yml exec postgres pg_isready -U postgres -q 2>/dev/null && break; \
	  sleep 1; \
	done
	@echo "▶  Applying migrations..."
	$(RUNTIME_ENV) cd backend && $(BACKEND_ENV) uv run alembic upgrade head
	@echo "✅  Infrastructure ready — Postgres :$$(sed -n 's/^DEV_POSTGRES_HOST_PORT=//p' $(RUNTIME_ENV_FILE)), Redis :$$(sed -n 's/^DEV_REDIS_HOST_PORT=//p' $(RUNTIME_ENV_FILE))"
	@echo "   Data is isolated under Docker project $(DEV_COMPOSE_PROJECT)"

dev-infra-stop:
	@echo "▶  Stopping branch-scoped dev stack $(DEV_COMPOSE_PROJECT)"
	$(RUNTIME_ENV) COMPOSE_PROJECT_NAME=$$DEV_COMPOSE_PROJECT docker compose -f docker-compose.dev.yml down

dev-backend:
	$(RUNTIME_ENV) cd backend && $(BACKEND_ENV) uv run uvicorn app.main:app \
	  --host 0.0.0.0 --port $$DEV_BACKEND_PORT --reload --reload-dir app --log-level $(BACKEND_LOG_LEVEL)

dev-worker:
	cd backend && $(BACKEND_ENV) uv run watchfiles "arq app.tasks.worker.WorkerSettings" app

dev-frontend:
	$(RUNTIME_ENV) cd frontend && VITE_PORT=$$VITE_PORT VITE_API_PROXY_TARGET=$$VITE_API_PROXY_TARGET npm run dev

dev:
	@echo "▶  Starting dev environment..."
	@$(RUNTIME_ENV)
	@echo "   Backend  →  http://localhost:$$(sed -n 's/^DEV_BACKEND_PORT=//p' $(RUNTIME_ENV_FILE))/"
	@echo "   Frontend →  http://localhost:$$(sed -n 's/^VITE_PORT=//p' $(RUNTIME_ENV_FILE))/"
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
	# Integration-only coverage is intentionally reported but cannot satisfy the
	# repository-wide threshold by itself. The combined test-backend-coverage
	# target remains the authoritative 75% unit+integration coverage gate.
	cd backend && $(BACKEND_ENV) uv run pytest tests/integration \
	  --cov=app --cov-report=term-missing --cov-report=html:coverage_html \
	  --cov-fail-under=0 \
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
	@$(MAKE) test-uplot-contract
	@$(MAKE) test-visual-policy

test-uplot-contract:
	@echo "▶  Primary workstation uPlot numerical-renderer contract..."
	$(WORKFLOW_PYTHON) tests/visual/validate-uplot-renderer-contract.py

test-visual-policy:
	@echo "▶  Deterministic TC2000 visual acceptance policy..."
	cd backend && .venv/bin/python ../tests/visual/validate-visual-acceptance-policy.py

test-compose-contract:
	@echo "▶  Compose and deployment contract validation..."
	SECRET_KEY=ci-contract-secret POSTGRES_PASSWORD=postgres CORS_ORIGINS='["http://localhost"]' BACKEND_IMAGE=charting-platform/backend:contract RESEARCH_RUNNER_IMAGE=charting-platform/research-runner:contract FRONTEND_IMAGE=charting-platform/frontend:contract POSTGRES_IMAGE=postgres:16-alpine REDIS_IMAGE=redis:7-alpine RPI_HTTP_PORT=8080 docker compose -f docker-compose.yml config >/dev/null
	SECRET_KEY=ci-contract-secret POSTGRES_PASSWORD=postgres CORS_ORIGINS='["http://localhost"]' BACKEND_IMAGE=charting-platform/backend:contract RESEARCH_RUNNER_IMAGE=charting-platform/research-runner:contract FRONTEND_IMAGE=charting-platform/frontend:contract POSTGRES_IMAGE=postgres:16-alpine REDIS_IMAGE=redis:7-alpine RPI_HTTP_PORT=8080 docker compose -f deploy/rpi/compose.yml config >/dev/null

test-migration-compatibility:
	@echo "▶  Fresh and previous-master migration compatibility gate..."
	$(WORKFLOW_PYTHON) scripts/validate-migration-compatibility.py

test-research-runner-probes:
	@echo "▶  Isolated research-runner sandbox/resource probes..."
	@$(RUNTIME_ENV) \
	  set -e; \
	  stage=container-discovery; \
	  trap 'status=$$?; if test "$$status" -ne 0; then printf "::error title=Research-runner probe failed::stage=%s exit=%s\\n" "$$stage" "$$status" >&2; fi' EXIT; \
	  container=$$(COMPOSE_PROJECT_NAME=$$STACK_COMPOSE_PROJECT docker compose ps -q research-runner); \
	  test -n "$$container" || (echo "research-runner container is missing" >&2; exit 1); \
	  stage=sandbox; printf '▶ research-runner probe stage: %s\n' "$$stage"; ./ops/probe-research-runner-sandbox.sh "$$container"; \
	  stage=resources; printf '▶ research-runner probe stage: %s\n' "$$stage"; ./ops/probe-research-runner-resources.sh "$$container"

test-live-provider-probes:
	@echo "▶  Risk-based reviewed live provider probes..."
	$(WORKFLOW_PYTHON) scripts/run-live-provider-probes.py

branch-tests:
	@test -n "$(INTEGRATION_BRANCH)" || (echo "INTEGRATION_BRANCH is required for branch-declared tests" >&2; exit 2)
	@$(RUNTIME_ENV) INTEGRATION_BRANCH="$(INTEGRATION_BRANCH)" $(WORKFLOW_PYTHON) scripts/run-branch-tests.py "$(INTEGRATION_BRANCH)"

validate-arm64-images:
	@echo "▶  Production application image build (linux/arm64)..."
	$(WORKFLOW_PYTHON) scripts/validate-arm64-images.py

test-e2e-install:
	@echo "▶  Ensuring Playwright Chromium is installed..."
	cd frontend && npx playwright install chromium

test-e2e: test-e2e-install
	@echo "▶  E2E tests (Playwright headless — stack must be running on :80)..."
	$(RUNTIME_ENV) cd frontend && STACK_URL=$${STACK_URL:-$$STACK_URL} npx playwright test

test-e2e-headed: test-e2e-install
	@echo "▶  E2E tests (Playwright headed)..."
	$(RUNTIME_ENV) cd frontend && STACK_URL=$${STACK_URL:-$$STACK_URL} npx playwright test --headed

test-stack-up:
	@$(RUNTIME_ENV)
	@echo "▶  Starting branch-scoped full application stack for browser validation..."
	@echo "   Branch  →  $(DEV_BRANCH_NAME)"
	@echo "   Project →  $(STACK_COMPOSE_PROJECT)"
	@echo "   Fixtures → instruments=$${E2E_SEED_INSTRUMENTS:-true}, market-data=$${E2E_SEED_MARKET_DATA:-false}"
	$(RUNTIME_ENV) E2E_SEED_INSTRUMENTS=$${E2E_SEED_INSTRUMENTS:-true} E2E_SEED_MARKET_DATA=$${E2E_SEED_MARKET_DATA:-false} COMPOSE_BAKE=$${COMPOSE_BAKE:-false} COMPOSE_PROJECT_NAME=$$STACK_COMPOSE_PROJECT POSTGRES_HOST_PORT=$$POSTGRES_HOST_PORT BACKEND_HOST_PORT=$$BACKEND_HOST_PORT FRONTEND_HOST_PORT=$$FRONTEND_HOST_PORT docker compose up -d --build --force-recreate --wait

test-stack-down:
	@echo "▶  Stopping branch-scoped full application stack $(STACK_COMPOSE_PROJECT)..."
	$(RUNTIME_ENV) COMPOSE_PROJECT_NAME=$$STACK_COMPOSE_PROJECT docker compose down -v

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

# ── Worktrees and integration ────────────────────────────────────────────────

worktree-create:
	@test -n "$(BRANCH)" || (echo "usage: make worktree-create BRANCH=feat/name" >&2; exit 2)
	@test -n "$(REQUEST)" || (echo "usage: make worktree-create BRANCH=feat/name REQUEST='exact human request'" >&2; exit 2)
	$(WORKFLOW_PYTHON) scripts/worktree.py create "$(BRANCH)" --request "$(REQUEST)" --base "$(if $(BASE),$(BASE),staging)" $(if $(PARENT_AUTHORIZATION),--dependency-authorization "$(PARENT_AUTHORIZATION)",)

worktree-list:
	$(WORKFLOW_PYTHON) scripts/worktree.py list

worktree-status:
	@test -n "$(BRANCH)" || (echo "usage: make worktree-status BRANCH=feat/name" >&2; exit 2)
	$(WORKFLOW_PYTHON) scripts/worktree.py status "$(BRANCH)"

worktree-overview:
	$(WORKFLOW_PYTHON) scripts/worktree.py overview

worktree-close:
	@test -n "$(BRANCH)" || (echo "usage: make worktree-close BRANCH=feat/name" >&2; exit 2)
	$(WORKFLOW_PYTHON) scripts/worktree.py close "$(BRANCH)"

worktree-archive:
	@test -n "$(BRANCH)" -a -n "$(CONFIRM)" || (echo "usage: make worktree-archive BRANCH=feat/name CONFIRM=feat/name" >&2; exit 2)
	$(WORKFLOW_PYTHON) scripts/worktree.py archive "$(BRANCH)" --confirm "$(CONFIRM)"

worktree-cleanup-report:
	@$(WORKFLOW_PYTHON) scripts/worktree-cleanup.py report

worktree-cleanup-reconcile:
	@$(WORKFLOW_PYTHON) scripts/worktree-cleanup.py reconcile

worktree-cleanup:
	@test "$(CONFIRM)" = "published-integration-candidates" || (echo "usage: make worktree-cleanup CONFIRM=published-integration-candidates" >&2; exit 2)
	$(WORKFLOW_PYTHON) scripts/worktree-cleanup.py cleanup --confirm "$(CONFIRM)"

branch-validate:
	$(WORKFLOW_PYTHON) scripts/validate-workstream.py ops/workstreams

integrate:
	@test -n "$(BRANCH)" || (echo "usage: make integrate BRANCH=feat/name" >&2; exit 2)
	$(WORKFLOW_PYTHON) scripts/integrate.py "$(BRANCH)" --publish $(if $(REMEDIATE_DEGRADED),--remediate-degraded,) $(if $(KEEP_PAUSED),--keep-paused,)

integrate-set:
	@test -n "$(BRANCHES)" || (echo "usage: make integrate-set BRANCHES='feat/a feat/b'" >&2; exit 2)
	$(WORKFLOW_PYTHON) scripts/integrate-set.py $(BRANCHES) --publish

validate-integration:
	@set -e; \
	stage=initialization; \
	trap 'status=$$?; if test "$$status" -ne 0; then printf "::error title=Integration gate failed::stage=%s exit=%s\n" "$$stage" "$$status" >&2; fi' EXIT; \
	stage=git-diff; printf '▶ integration gate stage: %s\n' "$$stage"; git diff --check; \
	stage=workstream; printf '▶ integration gate stage: %s\n' "$$stage"; $(MAKE) branch-validate; \
	stage=backend-dependencies; printf '▶ integration gate stage: %s\n' "$$stage"; (cd backend && uv lock --check && uv sync --frozen --dev && uv export --locked --format requirements-txt --output-file /tmp/charting-requirements.lock && sed '1,2d' requirements.txt > /tmp/charting-requirements.current && sed '1,2d' /tmp/charting-requirements.lock > /tmp/charting-requirements.generated && cmp -s /tmp/charting-requirements.generated /tmp/charting-requirements.current); \
	stage=migration-head; printf '▶ integration gate stage: %s\n' "$$stage"; (heads=$$(cd backend && uv run alembic heads | awk '/\(head\)/ { count += 1 } END { print count + 0 }'); test "$$heads" = 1); \
	stage=migration-compatibility; printf '▶ integration gate stage: %s\n' "$$stage"; $(MAKE) test-migration-compatibility; \
	stage=frontend-dependencies; printf '▶ integration gate stage: %s\n' "$$stage"; (cd frontend && npm ci); \
	stage=lint; printf '▶ integration gate stage: %s\n' "$$stage"; $(MAKE) lint; \
	stage=backend-coverage; printf '▶ integration gate stage: %s\n' "$$stage"; $(MAKE) test-backend-coverage; \
	stage=frontend-tests; printf '▶ integration gate stage: %s\n' "$$stage"; $(MAKE) test-fe; \
	stage=frontend-build; printf '▶ integration gate stage: %s\n' "$$stage"; (cd frontend && npm run build); \
	stage=compose-contract; printf '▶ integration gate stage: %s\n' "$$stage"; $(MAKE) test-compose-contract; \
	stage=provider-probes; printf '▶ integration gate stage: %s\n' "$$stage"; $(MAKE) test-live-provider-probes; \
	cleanup_stack() { $(MAKE) test-stack-down || true; }; \
	trap 'status=$$?; cleanup_stack; if test "$$status" -ne 0; then printf "::error title=Integration gate failed::stage=%s exit=%s\n" "$$stage" "$$status" >&2; fi' EXIT; \
	stage=stack-up; printf '▶ integration gate stage: %s\n' "$$stage"; E2E_SEED_MARKET_DATA=true $(MAKE) test-stack-up; \
	stage=research-runner-probes; printf '▶ integration gate stage: %s\n' "$$stage"; $(MAKE) test-research-runner-probes; \
	stage=e2e-functional; printf '▶ integration gate stage: %s\n' "$$stage"; E2E_SEED_MARKET_DATA=true $(MAKE) test-e2e; \
	stage=e2e-visual; printf '▶ integration gate stage: %s\\n' "$$stage"; ($(RUNTIME_ENV) cd frontend && STACK_URL=$${STACK_URL:-$$STACK_URL} E2E_SEED_MARKET_DATA=true RUN_BOARD_VISUAL_PARITY=1 npx playwright test tests/e2e/tc2000_visual.spec.ts); \
	if test -n "$(INTEGRATION_BRANCH)"; then stage=branch-tests; printf '▶ integration gate stage: %s\n' "$$stage"; $(MAKE) branch-tests INTEGRATION_BRANCH="$(INTEGRATION_BRANCH)"; fi; \
	stage=arm64-images; printf '▶ integration gate stage: %s\n' "$$stage"; $(MAKE) validate-arm64-images

# Narrow gate available only when the workstream contains the human-approved
# focused_only decision. Integration enforces that decision and its path scope.
validate-focused-integration:
	@set -e; \
	stage=git-diff; printf '▶ focused integration gate stage: %s\n' "$$stage"; git diff --check; \
	stage=workstream; printf '▶ focused integration gate stage: %s\n' "$$stage"; $(MAKE) branch-validate; \
	stage=workflow-syntax; printf '▶ focused integration gate stage: %s\n' "$$stage"; PYTHONPYCACHEPREFIX=/tmp/charting-platform-pycache $(WORKFLOW_PYTHON) -m py_compile scripts/worktree.py scripts/validate-workstream.py scripts/integrate.py; \
	stage=branch-tests; printf '▶ focused integration gate stage: %s\n' "$$stage"; $(MAKE) branch-tests INTEGRATION_BRANCH="$(INTEGRATION_BRANCH)"

rpi-preflight:
	$(WORKFLOW_PYTHON) scripts/rpi.py preflight

rpi-bundle:
	@test -n "$(COMMIT)" || (echo "usage: make rpi-bundle COMMIT=<full-master-sha>" >&2; exit 2)
	$(WORKFLOW_PYTHON) scripts/rpi.py bundle "$(COMMIT)"

deploy-rpi:
	@test -n "$(COMMIT)" -a -n "$(CONFIRM)" || (echo "usage: make deploy-rpi COMMIT=<sha> CONFIRM=<same-sha>" >&2; exit 2)
	$(WORKFLOW_PYTHON) scripts/rpi.py deploy "$(COMMIT)" "$(CONFIRM)"

rpi-status:
	$(WORKFLOW_PYTHON) scripts/rpi.py status
