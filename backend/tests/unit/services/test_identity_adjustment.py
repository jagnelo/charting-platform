"""Crypto and FX have no corporate actions, so raw history is the adjusted series."""

from datetime import UTC, datetime

from app.models.market_data_foundation import AdjustmentBasis
from app.models.ohlcv import OHLCVBar, Timeframe
from app.services.market_series import (
    IDENTITY_ADJUSTMENT_VERSION,
    asset_class_has_identity_adjustment,
    label_identity_adjusted,
    series_adjustment_is_compatible,
)


def test_only_asset_classes_without_corporate_actions_are_identity_adjusted():
    assert asset_class_has_identity_adjustment("Cryptocurrency") is True
    assert asset_class_has_identity_adjustment("Currency") is True
    for asset_class in ("Equity", "Exchange Traded Product", "Commodity", "Index", "", None):
        assert asset_class_has_identity_adjustment(asset_class) is False


def test_relabelled_raw_bars_are_read_back_by_adjusted_requests():
    bar = OHLCVBar(
        timeframe=Timeframe.D1,
        ts=datetime(2026, 11, 18, tzinfo=UTC),
        open=1,
        high=1,
        low=1,
        close=1,
        is_adjusted=False,
        adjustment_basis="raw",
        adjustment_version="provider-native",
    )

    (labelled,) = label_identity_adjusted([bar])

    assert labelled.is_adjusted is True
    assert labelled.adjustment_basis == "split_adjusted"
    assert labelled.adjustment_version == IDENTITY_ADJUSTMENT_VERSION

    class _Series:
        adjustment_basis = AdjustmentBasis(labelled.adjustment_basis)
        adjustment_version = labelled.adjustment_version

    assert series_adjustment_is_compatible(_Series(), True) is True
    assert series_adjustment_is_compatible(_Series(), False) is False
