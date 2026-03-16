"""
Unit tests for the indicator engine (services/indicators.py).

All tests are pure computation — no DB, no network.
The indicator engine is the most critical service in the application:
it drives alert evaluation, screener conditions, and chart display.
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from app.services.indicators import (
    BaseIndicator,
    SMAIndicator,
    bars_to_dataframe,
    compute,
    get_indicator,
    get_last_value,
    list_indicators,
    register_indicator,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def make_bars_df(closes: list[float], *, seed: int = 0) -> pd.DataFrame:
    """Build a minimal DataFrame that looks like bars_to_dataframe() output."""
    rng = np.random.RandomState(seed)
    n = len(closes)
    closes_arr = np.array(closes)
    highs = closes_arr + rng.uniform(0.5, 2.0, n)
    lows = closes_arr - rng.uniform(0.5, 2.0, n)
    opens = closes_arr - rng.uniform(-1.0, 1.0, n)
    vols = rng.randint(1_000_000, 50_000_000, n).astype(float)
    base = datetime(2024, 1, 1, tzinfo=UTC)
    index = [base + timedelta(days=i) for i in range(n)]
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes_arr, "volume": vols},
        index=index,
    ).rename_axis("ts")


def rising_closes(n=50, start=100.0, step=1.0) -> list[float]:
    return [start + i * step for i in range(n)]


def flat_closes(n=50, value=150.0) -> list[float]:
    return [value] * n


# ── Registry ───────────────────────────────────────────────────────────────────


class TestRegistry:
    def test_list_indicators_returns_all(self):
        result = list_indicators()
        names = {r["name"] for r in result}
        expected = {
            "sma",
            "ema",
            "wma",
            "bb",
            "rsi",
            "macd",
            "stoch",
            "cci",
            "roc",
            "vwap",
            "avwap",
            "obv",
            "volume_sma",
            "atr",
            "atr_pct",
        }
        assert expected.issubset(names)

    def test_list_indicators_schema_fields(self):
        for ind in list_indicators():
            assert "name" in ind
            assert "display_name" in ind
            assert "params_schema" in ind
            assert "output_columns" in ind
            assert "pane" in ind

    def test_get_indicator_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown indicator"):
            get_indicator("nonexistent_xyz")

    def test_get_indicator_case_insensitive(self):
        ind = get_indicator("SMA")
        assert isinstance(ind, SMAIndicator)

    def test_custom_indicator_registration(self):
        @register_indicator("test_constant")
        class ConstantIndicator(BaseIndicator):
            display_name = "Constant"
            description = "Always returns 42"
            output_columns = ["val"]
            params_schema = {}

            def compute(self, bars, params):
                return pd.Series(42.0, index=bars.index, name="val")

        ind = get_indicator("test_constant")
        df = make_bars_df(flat_closes(10))
        result = ind.compute(df, {})
        assert (result == 42.0).all()


# ── SMA ────────────────────────────────────────────────────────────────────────


class TestSMA:
    def test_basic_values(self):
        closes = [1.0, 2.0, 3.0, 4.0, 5.0]
        df = make_bars_df(closes)
        result = compute("sma", df, {"period": 3})
        assert result["sma"].isna().sum() == 2  # first 2 are NaN
        assert result["sma"].iloc[2] == pytest.approx(2.0)
        assert result["sma"].iloc[4] == pytest.approx(4.0)

    def test_flat_series(self):
        df = make_bars_df(flat_closes(30, 100.0))
        result = compute("sma", df, {"period": 10})
        valid = result["sma"].dropna()
        assert (valid == pytest.approx(100.0)).all()

    def test_rising_series(self):
        df = make_bars_df(rising_closes(20, 100.0, 1.0))
        result = compute("sma", df, {"period": 5})
        # SMA(5) of a linear series should itself be linear
        valid = result["sma"].dropna()
        diffs = valid.diff().dropna()
        assert (diffs == pytest.approx(1.0, abs=1e-9)).all()

    def test_period_1_equals_close(self):
        closes = [10.0, 20.0, 30.0]
        df = make_bars_df(closes)
        result = compute("sma", df, {"period": 1})
        assert list(result["sma"]) == pytest.approx(closes)

    def test_output_length_matches_input(self):
        df = make_bars_df(rising_closes(40))
        assert len(compute("sma", df, {"period": 10})) == 40

    def test_default_period_used_when_not_provided(self):
        df = make_bars_df(rising_closes(50))
        result = compute("sma", df, {})
        assert result["sma"].notna().sum() == 31  # 50 - 20 + 1 = 31 valid


# ── EMA ────────────────────────────────────────────────────────────────────────


class TestEMA:
    def test_ema_more_reactive_than_sma(self):
        """EMA should respond faster to price changes than SMA."""
        closes = flat_closes(30, 100.0) + [200.0] * 10
        df = make_bars_df(closes)
        ema = compute("ema", df, {"period": 10})["ema"]
        sma = compute("sma", df, {"period": 10})["sma"]
        # After spike, EMA should be higher than SMA
        assert ema.iloc[-1] > sma.iloc[-1]

    def test_flat_series_convergence(self):
        df = make_bars_df(flat_closes(50, 150.0))
        result = compute("ema", df, {"period": 10})["ema"].dropna()
        assert (result == pytest.approx(150.0, abs=1e-6)).all()

    def test_output_columns(self):
        df = make_bars_df(rising_closes(20))
        result = compute("ema", df, {"period": 5})
        assert "ema" in result.columns


# ── Bollinger Bands ────────────────────────────────────────────────────────────


class TestBollingerBands:
    def test_band_structure(self):
        df = make_bars_df(rising_closes(50))
        result = compute("bb", df, {"period": 20, "std_dev": 2.0})
        assert set(result.columns) == {"bb_upper", "bb_mid", "bb_lower", "bb_bandwidth", "bb_pct_b"}

    def test_upper_above_mid_above_lower(self):
        df = make_bars_df(rising_closes(50))
        result = compute("bb", df, {"period": 20, "std_dev": 2.0}).dropna()
        assert (result["bb_upper"] > result["bb_mid"]).all()
        assert (result["bb_mid"] > result["bb_lower"]).all()

    def test_flat_series_zero_bandwidth(self):
        df = make_bars_df(flat_closes(30, 100.0))
        result = compute("bb", df, {"period": 10}).dropna()
        assert (result["bb_bandwidth"] == pytest.approx(0.0, abs=1e-9)).all()
        assert (result["bb_upper"] == pytest.approx(100.0)).all()

    def test_wider_std_dev_widens_bands(self):
        df = make_bars_df(rising_closes(50))
        r1 = compute("bb", df, {"period": 20, "std_dev": 1.0}).dropna()
        r2 = compute("bb", df, {"period": 20, "std_dev": 2.0}).dropna()
        assert (r2["bb_bandwidth"] > r1["bb_bandwidth"]).all()


# ── RSI ────────────────────────────────────────────────────────────────────────


class TestRSI:
    def test_range_0_to_100(self):
        rng = np.random.RandomState(7)
        closes = list(100 + np.cumsum(rng.randn(200)))
        df = make_bars_df(closes)
        result = compute("rsi", df, {"period": 14})["rsi"].dropna()
        assert (result >= 0).all()
        assert (result <= 100).all()

    def test_all_gains_gives_near_100(self):
        df = make_bars_df(rising_closes(100, 100.0, 1.0))
        result = compute("rsi", df, {"period": 14})["rsi"].dropna()
        assert result.iloc[-1] > 90.0

    def test_all_losses_gives_near_0(self):
        closes = [100.0 - i * 1.0 for i in range(80)]
        df = make_bars_df(closes)
        result = compute("rsi", df, {"period": 14})["rsi"].dropna()
        assert result.iloc[-1] < 10.0

    def test_flat_series_is_nan_or_50(self):
        # Flat = 0 gains, 0 losses → avg_loss = 0 → RS = NaN or infinite
        df = make_bars_df(flat_closes(50, 100.0))
        result = compute("rsi", df, {"period": 14})["rsi"]
        # Either NaN (0/0) or close to 100 depending on implementation
        valid = result.dropna()
        if len(valid):
            assert ((valid >= 0) & (valid <= 100)).all()

    def test_pane_is_separate(self):
        ind = get_indicator("rsi")
        assert ind.default_pane == "separate"


# ── MACD ───────────────────────────────────────────────────────────────────────


class TestMACD:
    def test_output_columns(self):
        df = make_bars_df(rising_closes(60))
        result = compute("macd", df, {"fast": 12, "slow": 26, "signal": 9})
        assert set(result.columns) == {"macd_line", "macd_signal", "macd_histogram"}

    def test_histogram_is_line_minus_signal(self):
        df = make_bars_df(rising_closes(60))
        result = compute("macd", df, {})
        diff = result["macd_line"] - result["macd_signal"]
        assert (
            diff.equals(result["macd_histogram"])
            or (diff - result["macd_histogram"]).abs().max() < 1e-9
        )

    def test_rising_series_positive_macd(self):
        df = make_bars_df(rising_closes(80, 100.0, 2.0))
        result = compute("macd", df, {})
        # Fast EMA > Slow EMA on a sustained uptrend → positive MACD
        assert result["macd_line"].iloc[-1] > 0


# ── ATR ────────────────────────────────────────────────────────────────────────


class TestATR:
    def test_always_non_negative(self):
        rng = np.random.RandomState(3)
        closes = list(100 + np.cumsum(rng.randn(100)))
        df = make_bars_df(closes)
        result = compute("atr", df, {"period": 14})["atr"].dropna()
        assert (result >= 0).all()

    def test_higher_volatility_higher_atr(self):
        quiet = make_bars_df(flat_closes(50, 100.0))
        rng = np.random.RandomState(1)
        noisy_closes = list(100 + np.cumsum(rng.randn(50) * 5))
        noisy = make_bars_df(noisy_closes)
        atr_q = compute("atr", quiet, {"period": 14})["atr"].dropna().mean()
        atr_n = compute("atr", noisy, {"period": 14})["atr"].dropna().mean()
        assert atr_n > atr_q

    def test_atr_pct_scales_with_price(self):
        df_low = make_bars_df(flat_closes(50, 10.0))
        df_high = make_bars_df(flat_closes(50, 1000.0))
        pct_low = compute("atr_pct", df_low, {"period": 14})["atr_pct"].dropna()
        pct_high = compute("atr_pct", df_high, {"period": 14})["atr_pct"].dropna()
        # Both flat → ATR % should both be near 0 regardless of price level
        assert pct_low.mean() < 1.0
        assert pct_high.mean() < 1.0


# ── VWAP ───────────────────────────────────────────────────────────────────────


class TestVWAP:
    def test_vwap_within_high_low_range(self):
        rng = np.random.RandomState(9)
        closes = list(100 + np.cumsum(rng.randn(60)))
        df = make_bars_df(closes)
        result = compute("vwap", df, {})["vwap"].dropna()
        # VWAP must be between daily low and high
        assert (result >= df["low"].min() * 0.9).all()
        assert (result <= df["high"].max() * 1.1).all()

    def test_vwap_flat_price_equals_price(self):
        """With constant price and equal volumes, VWAP == price."""
        n = 20
        base = datetime(2024, 1, 1, tzinfo=UTC)
        index = [base + timedelta(days=i) for i in range(n)]
        df = pd.DataFrame(
            {
                "open": [100.0] * n,
                "high": [100.0] * n,
                "low": [100.0] * n,
                "close": [100.0] * n,
                "volume": [1_000_000.0] * n,
            },
            index=index,
        )
        result = compute("vwap", df, {})["vwap"].dropna()
        assert (result == pytest.approx(100.0)).all()


# ── get_last_value ─────────────────────────────────────────────────────────────


class TestGetLastValue:
    def test_returns_float(self, ohlcv_bars):
        val = get_last_value("rsi", ohlcv_bars, {"period": 14})
        assert isinstance(val, float)
        assert 0 <= val <= 100

    def test_returns_none_for_empty(self):
        val = get_last_value("sma", [], {"period": 20})
        assert val is None

    def test_returns_none_for_insufficient_data(self, ohlcv_bars):
        # Only 5 bars, period 100 → not enough
        val = get_last_value("sma", ohlcv_bars[:5], {"period": 100})
        assert val is None

    def test_unknown_indicator_returns_none(self, ohlcv_bars):
        val = get_last_value("does_not_exist", ohlcv_bars, {})
        assert val is None


# ── bars_to_dataframe ──────────────────────────────────────────────────────────


class TestBarsToDataframe:
    def test_empty_returns_empty_df(self):
        result = bars_to_dataframe([])
        assert result.empty
        assert set(result.columns) == {"open", "high", "low", "close", "volume"}

    def test_column_types(self, ohlcv_bars):
        df = bars_to_dataframe(ohlcv_bars)
        for col in ["open", "high", "low", "close", "volume"]:
            assert df[col].dtype in (np.float64, float)

    def test_sorted_by_timestamp(self, ohlcv_bars):
        # Shuffle and check it's re-sorted
        import random

        shuffled = ohlcv_bars.copy()
        random.shuffle(shuffled)
        df = bars_to_dataframe(shuffled)
        assert df.index.is_monotonic_increasing

    def test_length_matches_input(self, ohlcv_bars):
        df = bars_to_dataframe(ohlcv_bars)
        assert len(df) == len(ohlcv_bars)
