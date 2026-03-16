"""
Unit tests for the screener engine condition evaluation.

Tests _apply_operator and _evaluate_condition with mocked bars —
no DB container required for the pure logic tests.
Integration tests that run the full screener pipeline are in
tests/integration/tasks/test_screener.py.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.models.screener import ConditionOperator, ConditionSubject
from app.services.screener_engine import _apply_operator, _evaluate_condition


class TestApplyOperator:
    def test_gt(self):
        assert _apply_operator(ConditionOperator.GREATER_THAN, 50.0, None, 40.0) is True
        assert _apply_operator(ConditionOperator.GREATER_THAN, 30.0, None, 40.0) is False

    def test_lt(self):
        assert _apply_operator(ConditionOperator.LESS_THAN, 30.0, None, 40.0) is True
        assert _apply_operator(ConditionOperator.LESS_THAN, 50.0, None, 40.0) is False

    def test_gte(self):
        assert _apply_operator(ConditionOperator.GREATER_THAN_OR_EQ, 40.0, None, 40.0) is True
        assert _apply_operator(ConditionOperator.GREATER_THAN_OR_EQ, 39.9, None, 40.0) is False

    def test_lte(self):
        assert _apply_operator(ConditionOperator.LESS_THAN_OR_EQ, 40.0, None, 40.0) is True
        assert _apply_operator(ConditionOperator.LESS_THAN_OR_EQ, 40.1, None, 40.0) is False

    def test_equal_exact(self):
        assert _apply_operator(ConditionOperator.EQUAL, 42.0, None, 42.0) is True
        assert _apply_operator(ConditionOperator.EQUAL, 42.01, None, 42.0) is False

    def test_crosses_above(self):
        # prev=29, current=31, threshold=30 → crossed above
        assert _apply_operator(ConditionOperator.CROSSES_ABOVE, 31.0, 29.0, 30.0) is True
        # prev already above threshold → no crossing
        assert _apply_operator(ConditionOperator.CROSSES_ABOVE, 35.0, 32.0, 30.0) is False
        # still below
        assert _apply_operator(ConditionOperator.CROSSES_ABOVE, 25.0, 28.0, 30.0) is False

    def test_crosses_below(self):
        assert _apply_operator(ConditionOperator.CROSSES_BELOW, 28.0, 32.0, 30.0) is True
        assert _apply_operator(ConditionOperator.CROSSES_BELOW, 25.0, 27.0, 30.0) is False
        assert _apply_operator(ConditionOperator.CROSSES_BELOW, 35.0, 32.0, 30.0) is False

    def test_crosses_above_no_prev(self):
        """With no prev value, crossing cannot be detected → False."""
        assert _apply_operator(ConditionOperator.CROSSES_ABOVE, 35.0, None, 30.0) is False

    def test_percent_above(self):
        assert _apply_operator(ConditionOperator.PERCENT_ABOVE, 110.0, None, 100.0) is True
        assert _apply_operator(ConditionOperator.PERCENT_ABOVE, 90.0, None, 100.0) is False

    def test_percent_below(self):
        assert _apply_operator(ConditionOperator.PERCENT_BELOW, 90.0, None, 100.0) is True
        assert _apply_operator(ConditionOperator.PERCENT_BELOW, 110.0, None, 100.0) is False


class TestEvaluateCondition:
    def _make_condition(self, **kwargs):
        cond = MagicMock()
        cond.subject = kwargs.get("subject", ConditionSubject.PRICE)
        cond.operator = kwargs.get("operator", ConditionOperator.GREATER_THAN)
        cond.timeframe = MagicMock()
        cond.indicator_type = kwargs.get("indicator_type", None)
        cond.indicator_params = kwargs.get("indicator_params", {})
        cond.compare_indicator_type = kwargs.get("compare_indicator_type", None)
        cond.compare_indicator_params = kwargs.get("compare_indicator_params", None)
        cond.threshold_value = kwargs.get("threshold_value", Decimal("100"))
        return cond

    def _make_bar(self, close: float):
        bar = MagicMock()
        bar.close = Decimal(str(close))
        return bar

    def test_price_subject_gt(self):
        cond = self._make_condition(
            subject=ConditionSubject.PRICE,
            operator=ConditionOperator.GREATER_THAN,
            threshold_value=Decimal("100"),
        )
        bars = [self._make_bar(105.0)]
        prev_bars = [self._make_bar(95.0)]
        assert _evaluate_condition(cond, bars, prev_bars) is True

    def test_price_subject_not_met(self):
        cond = self._make_condition(
            subject=ConditionSubject.PRICE,
            operator=ConditionOperator.GREATER_THAN,
            threshold_value=Decimal("100"),
        )
        bars = [self._make_bar(95.0)]
        prev_bars = [self._make_bar(92.0)]
        assert _evaluate_condition(cond, bars, prev_bars) is False

    def test_empty_bars_returns_false(self):
        cond = self._make_condition()
        assert _evaluate_condition(cond, [], []) is False

    @patch("app.services.screener_engine.ind_engine.get_last_value")
    def test_indicator_subject_lt(self, mock_val):
        mock_val.return_value = 28.0  # RSI = 28, threshold = 30
        cond = self._make_condition(
            subject=ConditionSubject.INDICATOR,
            operator=ConditionOperator.LESS_THAN,
            indicator_type="rsi",
            indicator_params={"period": 14},
            threshold_value=Decimal("30"),
        )
        bars = [self._make_bar(100.0)] * 20
        assert _evaluate_condition(cond, bars, bars) is True

    @patch("app.services.screener_engine.ind_engine.get_last_value")
    def test_indicator_subject_none_returns_false(self, mock_val):
        mock_val.return_value = None
        cond = self._make_condition(
            subject=ConditionSubject.INDICATOR,
            operator=ConditionOperator.LESS_THAN,
            indicator_type="rsi",
            threshold_value=Decimal("30"),
        )
        bars = [self._make_bar(100.0)] * 5
        assert _evaluate_condition(cond, bars, bars) is False

    @patch("app.services.screener_engine.ind_engine.get_last_value")
    def test_indicator_cross_subject(self, mock_val):
        # EMA50 = 205 (prev=198), EMA200 = 203 (prev=200) → golden cross
        mock_val.side_effect = [205.0, 203.0, 198.0, 200.0]
        cond = self._make_condition(
            subject=ConditionSubject.INDICATOR_CROSS,
            operator=ConditionOperator.CROSSES_ABOVE,
            indicator_type="ema",
            indicator_params={"period": 50},
            compare_indicator_type="ema",
            compare_indicator_params={"period": 200},
            threshold_value=None,
        )
        bars = [self._make_bar(100.0)] * 60
        assert _evaluate_condition(cond, bars, bars) is True
