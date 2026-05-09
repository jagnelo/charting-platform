# Testing Guide

## Overview

The test suite is split into four layers. Each layer has a different speed/fidelity tradeoff:

| Layer | Tool | Speed | Requires containers | Coverage target |
|---|---|---|---|---|
| Backend unit | pytest | ~5s | No | ~90% of services |
| Backend integration | pytest + testcontainers | ~30s | Auto-started | ~85% of routers |
| Frontend unit | Vitest | ~3s | No | ~70% of stores/lib |
| Frontend E2E | Playwright | ~2 min | Stack running | 17 critical flows |

**Combined realistic coverage:** ~82% backend, ~70% frontend logic, ~65% whole system.

---

## Running Tests

### One-liner (recommended)

```bash
make test          # unit + integration + frontend unit (no E2E)
make test-all      # everything including E2E
make test-platform # branch-scoped full-stack validation
```

### Individually

```bash
# Backend unit tests only (fastest — no containers)
make test-unit

# Backend integration tests (testcontainers auto-starts Postgres + Redis)
make test-int

# Optional: point integration tests at already-running services
TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/charting_platform \
TEST_REDIS_URL=redis://localhost:6379/0 \
make test-int

# Frontend Vitest unit tests
make test-fe

# E2E — branch-scoped full stack
make test-stack-up
make test-e2e
```

### With coverage report

```bash
make test         # generates HTML reports
make coverage     # opens them in browser
```

Reports are written to:
- `backend/coverage_html/index.html` — backend line-by-line
- `frontend/coverage/index.html` — frontend

---

## Backend Test Structure

```
backend/tests/
├── conftest.py                     Root fixtures (containers, DB session, auth helpers)
├── unit/
│   ├── services/
│   │   ├── test_indicators.py      ~50 tests — all 14 indicators
│   │   ├── test_auth.py            JWT, bcrypt, token expiry
│   │   ├── test_alert_conditions.py Condition logic (no DB)
│   │   └── test_screener_engine.py  Operator + condition logic
│   └── models/
│       └── test_models.py          Constraints, cascades, relationships
└── integration/
    ├── api/
    │   ├── test_auth.py            Register, login, token refresh
    │   ├── test_alerts.py          Price + indicator alerts, isolation
    │   ├── test_radar.py           Radar runs, filters, details, overlays
    │   ├── test_screener.py        CRUD + run logic
    │   ├── test_drawings_presets.py Drawings, preset one-default rule
    │   └── test_instruments_ohlcv.py OHLCV caching, indicator endpoint
    ├── websocket/
    │   └── test_websocket.py       Connection, broadcast, disconnect
    └── tasks/
        └── test_background_tasks.py Alert engine, data pipeline
```

### Key design decisions

**Testcontainers** — integration tests spin up real Postgres and Redis containers using the `testcontainers` Python library. Containers start once per pytest session (scope=`"session"`). This means your first `make test-int` takes ~5 extra seconds; subsequent runs are fast.

**Service override escape hatch** — if Docker Desktop or testcontainers is flaky on a given machine, set `TEST_DATABASE_URL` and `TEST_REDIS_URL` to reuse an already-running Postgres/Redis pair. This keeps the same test logic and fixtures while avoiding container startup inside pytest.

**Transaction rollback isolation** — instead of truncating tables between tests (slow), each test runs inside a SQLAlchemy SAVEPOINT that is rolled back on teardown. This is ~10x faster and leaves zero state for the next test.

**Provider adapters are mocked** in integration tests — for example
`@patch("app.providers.yfinance.yf.Ticker")` in the current default setup.
We test our caching and routing logic, not third-party provider behavior.

**OneSignal is always mocked** — `@patch("app.tasks.alert_tasks.send_alert_notification")`. We assert it was called with the right arguments.

---

## Frontend Test Structure

```
frontend/tests/
├── unit/
│   ├── setup.ts                   Global mocks (uPlot, localStorage, fetch)
│   ├── lib/
│   │   ├── test_indicators.test.ts SMA, EMA, RSI, VWAP
│   │   ├── test_hit_test.test.ts  Drawing hit detection geometry
│   │   └── test_api_client.test.ts JWT auth, auto-refresh, error handling
│   └── stores/
│       ├── test_radar_store.test.ts Radar Pinia store flows
│       ├── test_instrument_info_panel.test.ts Day/52W hover provenance rendering
│       ├── test_chart_view_radar_handoff.test.ts Radar-to-chart preferred detection handoff
│       └── test_stores.test.ts    Auth, Chart, Alerts Pinia stores
└── e2e/
    ├── helpers.ts                 Page objects, custom test fixture
    └── flows.spec.ts              17 critical user flows including radar
```

### uPlot is mocked in unit tests

uPlot requires a real DOM canvas, which jsdom (Vitest's environment) doesn't fully support. All unit tests mock uPlot as a no-op. The actual chart rendering is covered by the E2E tests which run in a real Chromium browser.

### E2E test strategy

E2E tests use page objects (`LoginPage`, `ChartPage`, `ScreenerPage`) to keep tests readable and to isolate selector logic from test logic. If a selector changes, you update one place.

Tests are written to be **resilient to implementation details** — they check for visible text and navigation outcomes, not CSS classes or DOM structure. This minimises test churn when the UI is refactored.

Radar-specific frontend coverage now includes:

- radar store ordering / activation behavior
- `/radar` scan-lock behavior during manual runs
- `/radar` state-aware detail rendering and action-plan presentation
- timeframe-aware radar filtering, history loading, and outcome-summary loading
- radar-to-alert and radar-to-watchlist workflow actions
- dashboard radar widget timeframe rendering

Radar-specific backend coverage now includes:

- richer structure and setup-family classification
- AVWAP anchor behavior
- duplicate-thread-event dedupe across reruns
- timeframe-specific radar runs and filtering
- instrument history and outcome-summary endpoints
- radar alert/watchlist action endpoints
- forward-outcome evaluation fields (`outcome_status`, bars-since-signal, MFE/MAE)
- `/radar` setup-thread history rendering
- instrument-details day-range and 52-week occurrence hover text
- `/radar -> /chart` preferred detection handoff

Radar-specific backend coverage now also includes:

- candidate signal/context timestamps
- breakout-retest / breakdown-retest classification
- fakeout classification
- richer structure evidence (trendline / gap / pattern context)
- persisted action-level and state evidence fields
- setup-thread matching and event-index continuity helpers
- invalidated-transition integration coverage across repeat runs
- radar API state filtering and action-evidence responses

Radar-specific frontend coverage now also includes:

- saved radar view persistence
- dashboard radar widget loading/rendering
- `/chart` radar handoff and focused chart detection behavior

---

## Adding New Tests

### Adding a backend unit test

1. Find the right file in `tests/unit/` or create a new one
2. Add a class named `Test<Feature>` with methods named `test_<what_it_tests>`
3. Use the fixtures from `conftest.py` (`db`, `user`, `auth_headers`, `instrument`, `ohlcv_bars`)
4. Mark with `@pytest.mark.unit` if you want to run it in isolation

```python
class TestMyNewService:
    def test_does_the_right_thing(self, db, user):
        from app.services.my_service import do_thing
        result = do_thing(user.id, "some input")
        assert result == "expected output"
```

### Adding a new indicator test

The indicator tests in `tests/unit/services/test_indicators.py` follow a consistent pattern. For a new indicator `foo`:

```python
class TestFoo:
    def test_output_columns(self):
        df = make_bars_df(rising_closes(50))
        result = compute("foo", df, {})
        assert "foo_value" in result.columns   # match output_columns in your class

    def test_range(self):
        # Assert values stay in expected range

    def test_flat_series(self):
        # Assert behaviour on flat input
```

### Adding an E2E test

Add to `frontend/tests/e2e/flows.spec.ts` or create a new `*.spec.ts` file:

```typescript
test('F13 — my new feature works', async ({ page, loggedIn }) => {
  await page.goto('/my-page')
  await page.click('button:has-text("Do Thing")')
  await expect(page.locator('.result')).toBeVisible()
})
```

---

## Coverage Enforcement

The CI pipeline fails if coverage drops below the threshold:

| Threshold | Value | Config |
|---|---|---|
| Backend line coverage | 75% | `pytest.ini` `--cov-fail-under=75` |
| Frontend line coverage | 60% | `vitest.config.ts` `thresholds.lines` |

These thresholds are intentionally achievable. Raise them as the suite matures.

---

## CI

Tests run automatically on every push and pull request via GitHub Actions (`.github/workflows/ci.yml`):

1. **Backend unit** — fast, no containers
2. **Backend integration** — testcontainers
3. **Frontend unit** — Vitest
4. **E2E** — Playwright against a real branch-scoped Docker Compose stack spun up in CI/local workflows
