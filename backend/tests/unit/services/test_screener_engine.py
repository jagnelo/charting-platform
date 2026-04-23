"""
Unit tests for the screener engine condition evaluation.

Tests _compare (the pure comparison helper) and the logical-group
branch of _evaluate_condition (which is sync-compatible with mocked data).
No DB container required for these pure-logic tests.

Integration tests that run the full screener pipeline against a real DB
are in tests/integration/api/test_screener.py.
"""

import asyncio

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
    return asyncio.get_event_loop().run_until_complete(coro)


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
            "conditions": [
                {"type": "price_threshold", "field": "close", "op": "gt", "value": 50}
            ],
        }
        matched, _ = self._eval(condition, close=100.0)
        assert matched is False

    def test_not_negates_false(self):
        condition = {
            "operator": "NOT",
            "conditions": [
                {"type": "price_threshold", "field": "close", "op": "gt", "value": 999}
            ],
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
            "conditions": [
                {"type": "price_threshold", "field": "close", "op": "gt", "value": 50}
            ],
        }
        _, computed = self._eval(condition, close=100.0)
        assert "close" in computed
        assert computed["close"] == pytest.approx(100.0)
