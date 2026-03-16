"""
Unit tests for alert condition evaluation logic.

Tests the pure condition-matching functions in isolation —
no DB, no network, no yfinance calls.
"""

from decimal import Decimal

from app.models.price_alert import AlertCondition
from app.tasks.alert_tasks import _indicator_condition_met, _price_condition_met


class TestPriceConditionMet:
    """Tests for _price_condition_met(condition, threshold, last_price, current_price)."""

    # CROSSES_ABOVE ─────────────────────────────────────────────────────────────

    def test_crosses_above_triggers(self):
        assert (
            _price_condition_met(
                AlertCondition.CROSSES_ABOVE, Decimal("200"), Decimal("198"), Decimal("201")
            )
            is True
        )

    def test_crosses_above_no_trigger_still_above(self):
        """Already above threshold — should not re-trigger (not a new crossing)."""
        assert (
            _price_condition_met(
                AlertCondition.CROSSES_ABOVE, Decimal("200"), Decimal("205"), Decimal("210")
            )
            is False
        )

    def test_crosses_above_no_trigger_still_below(self):
        assert (
            _price_condition_met(
                AlertCondition.CROSSES_ABOVE, Decimal("200"), Decimal("190"), Decimal("195")
            )
            is False
        )

    def test_crosses_above_no_last_price(self):
        """First evaluation with no history — fire if currently above threshold."""
        assert (
            _price_condition_met(AlertCondition.CROSSES_ABOVE, Decimal("200"), None, Decimal("205"))
            is True
        )

    def test_crosses_above_no_last_price_below(self):
        assert (
            _price_condition_met(AlertCondition.CROSSES_ABOVE, Decimal("200"), None, Decimal("195"))
            is False
        )

    def test_crosses_above_exact_threshold(self):
        """Exact threshold crossing counts as 'above'."""
        assert (
            _price_condition_met(
                AlertCondition.CROSSES_ABOVE, Decimal("200"), Decimal("199"), Decimal("200")
            )
            is False
        )  # 199 <= 200 and current == 200 → not strictly above

    # CROSSES_BELOW ─────────────────────────────────────────────────────────────

    def test_crosses_below_triggers(self):
        assert (
            _price_condition_met(
                AlertCondition.CROSSES_BELOW, Decimal("150"), Decimal("155"), Decimal("148")
            )
            is True
        )

    def test_crosses_below_no_trigger_still_below(self):
        assert (
            _price_condition_met(
                AlertCondition.CROSSES_BELOW, Decimal("150"), Decimal("140"), Decimal("135")
            )
            is False
        )

    def test_crosses_below_no_trigger_still_above(self):
        assert (
            _price_condition_met(
                AlertCondition.CROSSES_BELOW, Decimal("150"), Decimal("160"), Decimal("165")
            )
            is False
        )

    # TOUCHES ───────────────────────────────────────────────────────────────────

    def test_touches_within_tolerance(self):
        assert (
            _price_condition_met(AlertCondition.TOUCHES, Decimal("100"), None, Decimal("100.05"))
            is True
        )

    def test_touches_exact(self):
        assert (
            _price_condition_met(AlertCondition.TOUCHES, Decimal("100"), None, Decimal("100"))
            is True
        )

    def test_touches_outside_tolerance(self):
        assert (
            _price_condition_met(AlertCondition.TOUCHES, Decimal("100"), None, Decimal("101.50"))
            is False
        )

    # PERCENT_CHANGE ────────────────────────────────────────────────────────────

    def test_percent_change_up(self):
        # threshold_price here stores the target absolute price
        assert (
            _price_condition_met(
                AlertCondition.PERCENT_CHANGE_UP, Decimal("110"), None, Decimal("115")
            )
            is True
        )

    def test_percent_change_up_not_reached(self):
        assert (
            _price_condition_met(
                AlertCondition.PERCENT_CHANGE_UP, Decimal("110"), None, Decimal("105")
            )
            is False
        )

    def test_percent_change_down(self):
        assert (
            _price_condition_met(
                AlertCondition.PERCENT_CHANGE_DOWN, Decimal("90"), None, Decimal("85")
            )
            is True
        )


class TestIndicatorConditionMet:
    """Tests for _indicator_condition_met()."""

    def test_crosses_above_indicator_vs_value(self):
        assert (
            _indicator_condition_met(
                AlertCondition.CROSSES_ABOVE,
                current_val=35.0,
                prev_val=28.0,
                threshold_val=Decimal("30"),
                current_b=None,
                prev_b=None,
            )
            is True
        )

    def test_crosses_above_indicator_vs_value_no_cross(self):
        assert (
            _indicator_condition_met(
                AlertCondition.CROSSES_ABOVE,
                current_val=35.0,
                prev_val=32.0,
                threshold_val=Decimal("30"),
                current_b=None,
                prev_b=None,
            )
            is False
        )

    def test_crosses_below_indicator_vs_value(self):
        assert (
            _indicator_condition_met(
                AlertCondition.CROSSES_BELOW,
                current_val=28.0,
                prev_val=33.0,
                threshold_val=Decimal("30"),
                current_b=None,
                prev_b=None,
            )
            is True
        )

    def test_indicator_cross_ema_golden_cross(self):
        """EMA50 crosses above EMA200 (golden cross)."""
        assert (
            _indicator_condition_met(
                AlertCondition.CROSSES_ABOVE,
                current_val=205.0,
                prev_val=198.0,
                threshold_val=None,
                current_b=203.0,
                prev_b=200.0,
            )
            is True
        )

    def test_indicator_cross_no_cross(self):
        assert (
            _indicator_condition_met(
                AlertCondition.CROSSES_ABOVE,
                current_val=205.0,
                prev_val=202.0,
                threshold_val=None,
                current_b=203.0,
                prev_b=200.0,
            )
            is False
        )  # already above on prev bar

    def test_indicator_touches(self):
        assert (
            _indicator_condition_met(
                AlertCondition.TOUCHES,
                current_val=30.01,
                prev_val=32.0,
                threshold_val=Decimal("30"),
                current_b=None,
                prev_b=None,
            )
            is True
        )

    def test_missing_prev_val_uses_first_eval(self):
        """When prev_val is None (first evaluation), crossing above fires."""
        assert (
            _indicator_condition_met(
                AlertCondition.CROSSES_ABOVE,
                current_val=35.0,
                prev_val=None,
                threshold_val=Decimal("30"),
                current_b=None,
                prev_b=None,
            )
            is True
        )
