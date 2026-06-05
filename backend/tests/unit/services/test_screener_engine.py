"""
Unit tests for the screener engine condition evaluation.

Tests _compare (the pure comparison helper) and the logical-group
branch of _evaluate_condition (which is sync-compatible with mocked data).
No DB container required for these pure-logic tests.

Integration tests that run the full screener pipeline against a real DB
are in tests/integration/api/test_screener.py.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from app.services.screener_engine import (
    _compare,
)

# ── _compare — pure operator dispatch ─────────────────────────────────────────


class TestCompare:
    def test_gt_true(self):
        assert _compare(50.0, "gt", 40.0) is True

    def test_gt_false(self):
        assert _compare(30.0, "gt", 40.0) is False

    def test_gt_equal_false(self):
        assert _compare(40.0, "gt", 40.0) is False

    def test_lt_true(self):
        assert _compare(30.0, "lt", 40.0) is True

    def test_lt_false(self):
        assert _compare(50.0, "lt", 40.0) is False

    def test_gte_equal(self):
        assert _compare(40.0, "gte", 40.0) is True

    def test_gte_above(self):
        assert _compare(40.1, "gte", 40.0) is True

    def test_gte_below(self):
        assert _compare(39.9, "gte", 40.0) is False

    def test_lte_equal(self):
        assert _compare(40.0, "lte", 40.0) is True

    def test_lte_below(self):
        assert _compare(39.9, "lte", 40.0) is True

    def test_lte_above(self):
        assert _compare(40.1, "lte", 40.0) is False

    def test_eq_exact(self):
        assert _compare(42.0, "eq", 42.0) is True

    def test_eq_nearly_equal(self):
        assert _compare(42.0 + 1e-10, "eq", 42.0) is True  # within tolerance

    def test_eq_not_equal(self):
        assert _compare(42.01, "eq", 42.0) is False

    def test_unknown_op_returns_false(self):
        assert _compare(50.0, "unknown_op", 40.0) is False


# ── _evaluate_condition — logical groups ──────────────────────────────────────


def _run(coro):
    """Helper: run a coroutine synchronously in tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestEvaluateConditionLogicGroups:
    """
    Test only the logical-group branch of _evaluate_condition.
    We compose groups of price_threshold leaves so we can reason about
    the results without mocking the indicator engine or a DB session.
    """

    def _make_ohlcv(self, close: float = 100.0):
        from app.services.indicators import OHLCVSeries

        n = 5
        ts = np.arange(n, dtype=np.int64) * 86400
        price = np.full(n, close, dtype=np.float64)
        return OHLCVSeries(
            timestamps=ts,
            opens=price,
            highs=price + 1,
            lows=price - 1,
            closes=price,
            volumes=np.ones(n) * 1_000_000,
        )

    def _make_instrument(self):
        from unittest.mock import MagicMock

        inst = MagicMock()
        inst.id = 1
        inst.equity_detail = None
        inst.stats = None
        return inst

    def _eval(self, condition: dict, close: float = 100.0):
        from app.models.ohlcv import Timeframe
        from app.services.screener_engine import _evaluate_condition

        data = self._make_ohlcv(close)
        instrument = self._make_instrument()
        db = None  # price_threshold branch doesn't use db
        return _run(_evaluate_condition(condition, data, instrument, Timeframe.D1, db))

    def test_and_both_true(self):
        condition = {
            "operator": "AND",
            "conditions": [
                {"type": "price_threshold", "field": "close", "op": "gt", "value": 50},
                {"type": "price_threshold", "field": "close", "op": "lt", "value": 200},
            ],
        }
        matched, _ = self._eval(condition, close=100.0)
        assert matched is True

    def test_and_one_false(self):
        condition = {
            "operator": "AND",
            "conditions": [
                {"type": "price_threshold", "field": "close", "op": "gt", "value": 50},
                {"type": "price_threshold", "field": "close", "op": "gt", "value": 999},
            ],
        }
        matched, _ = self._eval(condition, close=100.0)
        assert matched is False

    def test_or_one_true(self):
        condition = {
            "operator": "OR",
            "conditions": [
                {"type": "price_threshold", "field": "close", "op": "gt", "value": 999},
                {"type": "price_threshold", "field": "close", "op": "gt", "value": 50},
            ],
        }
        matched, _ = self._eval(condition, close=100.0)
        assert matched is True

    def test_or_both_false(self):
        condition = {
            "operator": "OR",
            "conditions": [
                {"type": "price_threshold", "field": "close", "op": "gt", "value": 999},
                {"type": "price_threshold", "field": "close", "op": "gt", "value": 500},
            ],
        }
        matched, _ = self._eval(condition, close=100.0)
        assert matched is False

    def test_not_negates_true(self):
        condition = {
            "operator": "NOT",
            "conditions": [{"type": "price_threshold", "field": "close", "op": "gt", "value": 50}],
        }
        matched, _ = self._eval(condition, close=100.0)
        assert matched is False

    def test_not_negates_false(self):
        condition = {
            "operator": "NOT",
            "conditions": [{"type": "price_threshold", "field": "close", "op": "gt", "value": 999}],
        }
        matched, _ = self._eval(condition, close=100.0)
        assert matched is True

    def test_nested_and_within_or(self):
        """OR[ AND[false,false], AND[true,true] ] → True."""
        condition = {
            "operator": "OR",
            "conditions": [
                {
                    "operator": "AND",
                    "conditions": [
                        {"type": "price_threshold", "field": "close", "op": "gt", "value": 999},
                        {"type": "price_threshold", "field": "close", "op": "gt", "value": 500},
                    ],
                },
                {
                    "operator": "AND",
                    "conditions": [
                        {"type": "price_threshold", "field": "close", "op": "gt", "value": 50},
                        {"type": "price_threshold", "field": "close", "op": "lt", "value": 200},
                    ],
                },
            ],
        }
        matched, _ = self._eval(condition, close=100.0)
        assert matched is True

    def test_empty_and_is_vacuously_true(self):
        """AND with no conditions: all([]) == True."""
        condition = {"operator": "AND", "conditions": []}
        matched, _ = self._eval(condition, close=100.0)
        assert matched is True

    def test_price_threshold_computed_values_present(self):
        condition = {
            "operator": "AND",
            "conditions": [{"type": "price_threshold", "field": "close", "op": "gt", "value": 50}],
        }
        _, computed = self._eval(condition, close=100.0)
        assert "close" in computed
        assert computed["close"] == pytest.approx(100.0)


class TestEvaluateConditionIndicatorAndPeriodBranches:
    def _make_ohlcv(self, closes: list[float], *, step_days: int = 1):
        from app.services.indicators import OHLCVSeries

        start = datetime.now(UTC) - timedelta(days=(len(closes) - 1) * step_days)
        timestamps = np.array(
            [int((start + timedelta(days=i * step_days)).timestamp()) for i in range(len(closes))],
            dtype=np.int64,
        )
        close_arr = np.array(closes, dtype=np.float64)
        return OHLCVSeries(
            timestamps=timestamps,
            opens=close_arr.copy(),
            highs=close_arr + 1,
            lows=close_arr - 1,
            closes=close_arr,
            volumes=np.full(len(closes), 1_000_000.0),
        )

    def _make_instrument(self):
        from unittest.mock import MagicMock

        inst = MagicMock()
        inst.id = 99
        inst.equity_detail = None
        inst.stats = None
        return inst

    def _eval(self, condition: dict, data, monkeypatch, *, timeframe=None):
        from app.models.ohlcv import Timeframe
        from app.services.screener_engine import _evaluate_condition

        instrument = self._make_instrument()
        tf = timeframe or Timeframe.D1
        return _run(_evaluate_condition(condition, data, instrument, tf, db=None))

    def test_indicator_threshold_uses_latest_non_nan_value(self, monkeypatch):
        async def fake_compute(*_args, **_kwargs):
            return {"rsi": np.array([np.nan, 45.0, 61.5])}

        monkeypatch.setattr(
            "app.services.screener_engine._compute_indicator_cached",
            fake_compute,
        )

        matched, computed = self._eval(
            {
                "type": "indicator_threshold",
                "indicator": "rsi",
                "params": {"period": 14},
                "op": "gt",
                "value": 60,
            },
            self._make_ohlcv([100, 101, 102]),
            monkeypatch,
        )

        assert matched is True
        assert computed["rsi_rsi"] == pytest.approx(61.5)

    def test_indicator_cross_detects_crosses_above(self, monkeypatch):
        async def fake_compute(_db, _instrument_id, _timeframe, indicator_type, _params, _data):
            if indicator_type == "ema":
                return {"ema": np.array([10.0, 11.0, 15.0])}
            return {"sma": np.array([12.0, 12.0, 13.0])}

        monkeypatch.setattr(
            "app.services.screener_engine._compute_indicator_cached",
            fake_compute,
        )

        matched, computed = self._eval(
            {
                "type": "indicator_cross",
                "indicator_a": {"type": "ema", "params": {"period": 10}},
                "indicator_b": {"type": "sma", "params": {"period": 20}},
                "op": "crosses_above",
            },
            self._make_ohlcv([100, 101, 102]),
            monkeypatch,
        )

        assert matched
        assert computed["ema_latest"] == pytest.approx(15.0)
        assert computed["sma_latest"] == pytest.approx(13.0)

    def test_indicator_threshold_can_target_named_output_series(self, monkeypatch):
        async def fake_compute(*_args, **_kwargs):
            return {
                "bb_upper": np.array([np.nan, 120.0, 121.5]),
                "bb_mid": np.array([np.nan, 100.0, 101.0]),
                "bb_lower": np.array([np.nan, 80.0, 81.5]),
            }

        monkeypatch.setattr(
            "app.services.screener_engine._compute_indicator_cached",
            fake_compute,
        )

        matched, computed = self._eval(
            {
                "type": "indicator_threshold",
                "indicator": "bb",
                "params": {"period": 20, "std_dev": 2},
                "output": "bb_lower",
                "op": "gt",
                "value": 81,
            },
            self._make_ohlcv([100, 101, 102]),
            monkeypatch,
        )

        assert matched is True
        assert computed["bb_bb_lower"] == pytest.approx(81.5)

    def test_price_change_period_uses_calendar_window(self, monkeypatch):
        data = self._make_ohlcv([100.0, 110.0, 120.0], step_days=2)

        matched, computed = self._eval(
            {
                "type": "price_change_period",
                "period": "1W",
                "op": "gt",
                "value": 0.15,
            },
            data,
            monkeypatch,
        )

        assert matched is True
        assert computed["price_change"] == pytest.approx(0.2)

    def test_performance_uses_daily_bars_when_timeframe_is_not_daily(self, monkeypatch):
        from app.models.ohlcv import Timeframe

        weekly_data = self._make_ohlcv([100.0, 105.0, 110.0], step_days=7)
        daily_data = self._make_ohlcv([100.0, 104.0, 112.0], step_days=2)

        async def fake_load_bars(_db, _instrument_id, requested_timeframe):
            assert requested_timeframe == Timeframe.D1
            return daily_data

        monkeypatch.setattr("app.services.screener_engine._load_bars", fake_load_bars)

        matched, computed = self._eval(
            {
                "type": "performance",
                "period": "1W",
                "op": "gt",
                "value": 0.1,
            },
            weekly_data,
            monkeypatch,
            timeframe=Timeframe.W1,
        )

        assert matched is True
        assert computed["performance"] == pytest.approx(0.12)
