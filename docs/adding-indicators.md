# Adding a New Indicator

The indicator system is registry-based. Adding a new indicator requires touching **exactly one file** — `backend/app/services/indicators.py`. Everything else (API endpoint, alert engine, screener, frontend picker) picks it up automatically.

---

## Step 1 — Write the class

Open `backend/app/services/indicators.py` and add your class anywhere after the base class definition:

```python
@register_indicator("my_indicator")   # canonical name, lowercase
class MyIndicator(BaseIndicator):
    display_name   = "My Indicator"
    description    = "One-line description shown in the UI picker."
    params_schema  = {
        "period": {"type": "int", "default": 14, "min": 1, "max": 200},
        "factor": {"type": "float", "default": 2.0, "min": 0.1, "max": 10.0},
    }
    output_columns = ["my_indicator"]     # list of column names this indicator produces
    default_pane   = "main"               # "main" or "separate" (sub-pane below chart)

    def compute(self, bars: pd.DataFrame, params: dict) -> pd.Series:
        period = int(self._p(params, "period"))
        factor = float(self._p(params, "factor"))
        # bars has columns: open, high, low, close, volume
        # Return a Series (or DataFrame if output_columns has >1 entry)
        result = bars["close"].rolling(period).mean() * factor
        return result.rename("my_indicator")
```

**Rules:**
- Return `pd.Series` for single-output indicators, `pd.DataFrame` for multi-output (e.g. Bollinger Bands)
- Column names in the return value must match `output_columns`
- Return `NaN` for rows with insufficient data — never `None` or `0`
- Do not raise for insufficient data; let pandas handle it naturally via `min_periods`
- `self._p(params, "key")` gets a param with automatic fallback to the schema default

---

## Step 2 — Add a frontend mirror (optional, for display performance)

The backend is the authoritative computation source. The frontend mirrors indicators in TypeScript so charts update instantly without a round-trip when you add/configure an indicator.

Create `frontend/src/lib/uplot/indicators/my_indicator.ts`:

```typescript
export function computeMyIndicator(
  closes: number[],
  period = 14,
  factor = 2.0,
): (number | null)[] {
  return closes.map((_, i) => {
    if (i < period - 1) return null
    const slice = closes.slice(i - period + 1, i + 1)
    const mean = slice.reduce((a, b) => a + b, 0) / period
    return mean * factor
  })
}
```

Then register it in `UPlotChart.vue` inside `computeIndicatorSeries()`:

```typescript
case 'my_indicator':
  return computeMyIndicator(
    closes,
    (i.params.period as number) ?? 14,
    (i.params.factor as number) ?? 2.0,
  )
```

If you don't add a frontend mirror, the indicator will still appear in the picker and work for alerts and screeners — the chart will just fetch values from `GET /api/v1/indicators/compute/{symbol}/{timeframe}?indicator=my_indicator` instead of computing locally.

---

## Step 3 — Write tests

Add a test class to `backend/tests/unit/services/test_indicators.py`:

```python
class TestMyIndicator:
    def test_output_columns(self):
        df = make_bars_df(rising_closes(50))
        result = compute("my_indicator", df, {"period": 10, "factor": 1.0})
        assert "my_indicator" in result.columns

    def test_flat_series(self):
        df = make_bars_df(flat_closes(30, 100.0))
        result = compute("my_indicator", df, {"period": 10, "factor": 1.0})
        valid = result["my_indicator"].dropna()
        assert (valid == pytest.approx(100.0)).all()

    def test_insufficient_data_returns_nan(self):
        df = make_bars_df(rising_closes(5))
        result = compute("my_indicator", df, {"period": 10})
        # Period > data length → all NaN
        assert result["my_indicator"].isna().all()
```

---

## That's it

After adding the class, the indicator is immediately available for:

- `GET /api/v1/indicators/` — appears in the registry list
- `GET /api/v1/indicators/compute/{symbol}/{tf}?indicator=my_indicator` — computable via API
- Alert creation — available as `indicator_type` in `POST /api/v1/indicator-alerts/`
- Screener conditions — available as `indicator_type` in screener condition objects
- Frontend picker — appears automatically (fetched from the API)

No router changes, no schema changes, no migration needed.
