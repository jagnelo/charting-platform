"""
Unit tests for the current function-based indicator engine.

These tests cover the backend indicator API used by charts, alerts, and
screeners: OHLCVSeries normalisation, metadata listing, parameter alias
normalisation, indicator computation, and latest-value extraction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.services.indicators import (
    INDICATOR_REGISTRY,
    OHLCVSeries,
    compute_indicator,
    get_latest_value,
    list_indicators,
    normalize_indicator_params,
)


@dataclass
class FakeBar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


def make_series(
    closes: list[float],
    *,
    seed: int = 0,
    start: datetime | None = None,
    step: timedelta = timedelta(days=1),
) -> OHLCVSeries:
    rng = np.random.RandomState(seed)
    start = start or datetime(2024, 1, 1, tzinfo=UTC)
    closes_arr = np.array(closes, dtype=np.float64)
    highs = closes_arr + rng.uniform(0.5, 2.0, len(closes))
    lows = closes_arr - rng.uniform(0.5, 2.0, len(closes))
    opens = closes_arr + rng.uniform(-1.0, 1.0, len(closes))
    volumes = rng.randint(1_000_000, 5_000_000, len(closes)).astype(np.float64)
    timestamps = np.array(
        [int((start + i * step).timestamp()) for i in range(len(closes))],
        dtype=np.int64,
    )
    return OHLCVSeries(
        timestamps=timestamps,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes_arr,
        volumes=volumes,
    )


def rising_closes(n: int = 80, start: float = 100.0, step: float = 1.0) -> list[float]:
    return [start + i * step for i in range(n)]


def falling_closes(n: int = 80, start: float = 180.0, step: float = 1.0) -> list[float]:
    return [start - i * step for i in range(n)]


def flat_closes(n: int = 80, value: float = 150.0) -> list[float]:
    return [value] * n


class TestOHLCVSeries:
    def test_from_orm_bars_empty(self):
        series = OHLCVSeries.from_orm_bars([])
        assert len(series.timestamps) == 0
        assert len(series.closes) == 0

    def test_from_orm_bars_maps_values(self):
        bars = [
            FakeBar(
                ts=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i),
                open=100 + i,
                high=101 + i,
                low=99 + i,
                close=100.5 + i,
                volume=1_000_000 + i,
            )
            for i in range(3)
        ]
        series = OHLCVSeries.from_orm_bars(bars)
        assert series.timestamps.dtype == np.int64
        assert series.opens.dtype == np.float64
        assert series.closes.tolist() == pytest.approx([100.5, 101.5, 102.5])

    def test_to_dataframe_has_expected_columns(self):
        series = make_series(rising_closes(5))
        df = series.to_dataframe()
        assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
        assert len(df) == 5


class TestIndicatorMetadata:
    def test_registry_contains_expected_high_value_indicators(self):
        expected = {
            "sma",
            "ema",
            "rsi",
            "macd",
            "bb",
            "vwap",
            "avwap",
            "atr",
            "stoch",
            "obv",
            "adx",
            "ichimoku",
            "psar",
            "donchian",
            "keltner",
            "williams_r",
            "mfi",
            "roc",
            "pivot_points",
            "cmf",
            "ppo",
        }
        assert expected.issubset(set(INDICATOR_REGISTRY))

    def test_list_indicators_exposes_expected_shape(self):
        items = list_indicators()
        assert items
        first = items[0]
        assert "type" in first
        assert "label" in first
        assert "description" in first
        assert "pane" in first
        assert "output_keys" in first
        assert "params" in first

    def test_list_indicators_matches_registry(self):
        listed = {item["type"] for item in list_indicators()}
        assert listed == set(INDICATOR_REGISTRY)


class TestParamNormalisation:
    def test_bb_multiplier_alias_maps_to_std_dev(self):
        params = normalize_indicator_params("bb", {"multiplier": 2.5})
        assert params == {"std_dev": 2.5}

    def test_camel_case_aliases_are_normalized(self):
        params = normalize_indicator_params(
            "ichimoku",
            {"senkouB": 60, "afStart": 0.01, "afStep": 0.03, "afMax": 0.25},
        )
        assert params["senkou_b"] == 60
        assert params["af_start"] == 0.01
        assert params["af_step"] == 0.03
        assert params["af_max"] == 0.25

    def test_stoch_period_alias_maps_to_k_period(self):
        params = normalize_indicator_params("stoch", {"period": 21, "smoothK": 5})
        assert params["k_period"] == 21
        assert params["smooth_k"] == 5


class TestIndicatorComputation:
    def test_unknown_indicator_raises_key_error(self):
        with pytest.raises(KeyError):
            compute_indicator("does_not_exist", make_series(rising_closes(20)))

    def test_sma_period_one_equals_close(self):
        closes = [10.0, 20.0, 30.0, 40.0]
        result = compute_indicator("sma", make_series(closes), {"period": 1})["sma"]
        assert result.tolist() == pytest.approx(closes)

    def test_ema_reacts_faster_than_sma_after_jump(self):
        closes = flat_closes(40, 100.0) + flat_closes(3, 200.0)
        data = make_series(closes)
        ema = compute_indicator("ema", data, {"period": 10})["ema"]
        sma = compute_indicator("sma", data, {"period": 10})["sma"]
        assert ema[-1] > sma[-1]

    def test_rsi_uptrend_finishes_high(self):
        rsi = compute_indicator("rsi", make_series(rising_closes(120)), {"period": 14})["rsi"]
        assert np.nanmax(rsi) <= 100
        assert np.nanmin(rsi) >= 0
        assert rsi[~np.isnan(rsi)][-1] > 90

    def test_rsi_downtrend_finishes_low(self):
        rsi = compute_indicator("rsi", make_series(falling_closes(120)), {"period": 14})["rsi"]
        assert rsi[~np.isnan(rsi)][-1] < 10

    def test_macd_histogram_matches_difference(self):
        result = compute_indicator("macd", make_series(rising_closes(120)))
        diff = result["macd"] - result["signal"]
        mask = ~(np.isnan(diff) | np.isnan(result["histogram"]))
        assert np.allclose(diff[mask], result["histogram"][mask])

    def test_bollinger_band_ordering(self):
        result = compute_indicator(
            "bb", make_series(rising_closes(80)), {"period": 20, "std_dev": 2.0}
        )
        upper = result["bb_upper"]
        mid = result["bb_mid"]
        lower = result["bb_lower"]
        mask = ~(np.isnan(upper) | np.isnan(mid) | np.isnan(lower))
        assert np.all(upper[mask] > mid[mask])
        assert np.all(mid[mask] > lower[mask])

    def test_vwap_flat_series_matches_price(self):
        price = np.full(30, 100.0)
        timestamps = np.array(
            [
                int((datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=i)).timestamp())
                for i in range(30)
            ],
            dtype=np.int64,
        )
        series = OHLCVSeries(
            timestamps=timestamps,
            opens=price.copy(),
            highs=price.copy(),
            lows=price.copy(),
            closes=price.copy(),
            volumes=np.full(30, 1_000_000.0),
        )
        vwap = compute_indicator("vwap", series)["vwap"]
        assert np.allclose(vwap, np.full(30, 100.0))

    def test_avwap_before_anchor_is_nan(self):
        series = make_series(rising_closes(20))
        anchor = int(series.timestamps[10])
        avwap = compute_indicator("avwap", series, {"anchor_timestamp": anchor})["avwap"]
        assert np.isnan(avwap[:10]).all()
        assert not np.isnan(avwap[10:]).all()

    def test_atr_is_non_negative(self):
        atr = compute_indicator("atr", make_series(rising_closes(80)), {"period": 14})["atr"]
        valid = atr[~np.isnan(atr)]
        assert np.all(valid >= 0)

    def test_stoch_outputs_in_expected_range(self):
        result = compute_indicator("stoch", make_series(rising_closes(80)))
        for key in ("stoch_k", "stoch_d"):
            vals = result[key][~np.isnan(result[key])]
            assert np.all(vals >= 0)
            assert np.all(vals <= 100)

    def test_obv_returns_full_length_series(self):
        obv = compute_indicator("obv", make_series(rising_closes(25)))["obv"]
        assert len(obv) == 25
        assert not np.isnan(obv).all()

    def test_adx_returns_all_expected_series(self):
        result = compute_indicator("adx", make_series(rising_closes(120)))
        assert set(result) == {"adx", "plus_di", "minus_di"}

    def test_ichimoku_returns_all_expected_series(self):
        result = compute_indicator("ichimoku", make_series(rising_closes(120)))
        assert set(result) == {
            "ichimoku_tenkan",
            "ichimoku_kijun",
            "ichimoku_senkou_a",
            "ichimoku_senkou_b",
            "ichimoku_chikou",
        }

    def test_pivot_points_output_shape(self):
        result = compute_indicator("pivot_points", make_series(rising_closes(40)))
        assert set(result) == {"pp", "r1", "r2", "r3", "s1", "s2", "s3"}

    def test_raw_price_indicator_matches_input(self):
        series = make_series(rising_closes(10))
        close = compute_indicator("close", series)["close"]
        assert np.array_equal(close, series.closes)

    def test_invalid_param_type_falls_back_to_nan_series(self):
        series = make_series(rising_closes(10))
        result = compute_indicator("sma", series, {"period": "not_an_int"})
        assert set(result) == {"sma"}
        assert np.isnan(result["sma"]).all()


class TestGetLatestValue:
    def test_returns_latest_non_nan_value(self):
        series = make_series(rising_closes(60))
        latest = get_latest_value("sma", series, {"period": 20})
        expected = np.mean(series.closes[-20:])
        assert latest == pytest.approx(expected)

    def test_output_key_selects_secondary_series(self):
        series = make_series(rising_closes(120))
        latest_hist = get_latest_value("macd", series, output_key="histogram")
        assert latest_hist is not None

    def test_all_nan_returns_none(self):
        series = make_series(flat_closes(5, 100.0))
        assert get_latest_value("sma", series, {"period": 50}) is None
