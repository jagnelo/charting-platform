# Testing Guide

## Overview

The test suite is split into four layers. Each layer has a different speed/fidelity tradeoff:

| Layer | Tool | Speed | Requires containers | Coverage target |
|---|---|---|---|---|
| Backend unit | pytest | ~5s | No | ~90% of services |
| Backend integration | pytest + testcontainers | ~30s | Auto-started | ~85% of routers |
| Frontend unit | Vitest | ~3s | No | ~70% of stores/lib |
| Frontend E2E | Playwright | ~2 min | Stack running | 12 critical flows |

**Combined realistic coverage:** ~82% backend, ~70% frontend logic, ~65% whole system.

---

## Running Tests

### One-liner (recommended)

```bash
make test          # unit + integration + frontend unit (no E2E)
make test-all      # everything including E2E
```

### Individually

```bash
# Backend unit tests only (fastest — no containers)
make test-unit

# Backend integration tests (testcontainers auto-starts Postgres + Redis)
make test-int

# Frontend Vitest unit tests
make test-fe

# E2E — requires docker compose up -d first
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

**Transaction rollback isolation** — instead of truncating tables between tests (slow), each test runs inside a SQLAlchemy SAVEPOINT that is rolled back on teardown. This is ~10x faster and leaves zero state for the next test.

**yfinance is always mocked** in integration tests — `@patch("app.services.market_data.yf.Ticker")`. We test our caching and routing logic, not yfinance's reliability.

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
│       └── test_stores.test.ts    Auth, Chart, Alerts Pinia stores
└── e2e/
    ├── helpers.ts                 Page objects, custom test fixture
    └── flows.spec.ts              12 critical user flows
```

### uPlot is mocked in unit tests

uPlot requires a real DOM canvas, which jsdom (Vitest's environment) doesn't fully support. All unit tests mock uPlot as a no-op. The actual chart rendering is covered by the E2E tests which run in a real Chromium browser.

### E2E test strategy

E2E tests use page objects (`LoginPage`, `ChartPage`, `ScreenerPage`) to keep tests readable and to isolate selector logic from test logic. If a selector changes, you update one place.

Tests are written to be **resilient to implementation details** — they check for visible text and navigation outcomes, not CSS classes or DOM structure. This minimises test churn when the UI is refactored.

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
4. **E2E** — Playwright against a real Docker Compose stack spun up in CI
