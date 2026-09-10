from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import MarketBarObservation
from app.services.ohlcv_coverage import reconcile_ohlcv_storage


def _bar(
    *,
    ts: datetime,
    source_id: int | None,
    derived: bool = False,
    close: str = "10",
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
):
    return OHLCVBar(
        instrument_id=1,
        data_source_id=source_id,
        timeframe=timeframe,
        ts=ts,
        open=Decimal("9"),
        high=Decimal("11"),
        low=Decimal("8"),
        close=Decimal(close),
        volume=Decimal("100"),
        vwap=Decimal("10"),
        is_adjusted=adjusted,
        is_derived=derived,
    )


def _observation(
    *,
    ts: datetime,
    source_id: int,
    close: str = "10",
    timeframe: Timeframe = Timeframe.D1,
    adjusted: bool = True,
):
    return MarketBarObservation(
        instrument_id=1,
        data_source_id=source_id,
        timeframe=timeframe,
        ts=ts,
        observed_at=ts,
        open=Decimal("9"),
        high=Decimal("11"),
        low=Decimal("8"),
        close=Decimal(close),
        volume=Decimal("100"),
        vwap=Decimal("10"),
        is_adjusted=adjusted,
    )


def test_reconciles_provider_bars_and_ignores_derived_rows_without_observations():
    timestamp = datetime(2026, 1, 2, tzinfo=UTC)

    result = reconcile_ohlcv_storage(
        [
            _bar(ts=timestamp, source_id=7),
            _bar(ts=timestamp + timedelta(days=1), source_id=None, derived=True),
        ],
        [_observation(ts=timestamp, source_id=7)],
    )

    assert result.status == "reconciled"
    assert result.provider_bar_count == 1
    assert result.observation_count == 1
    assert result.matched_observation_count == 1
    assert result.missing_observation_count == 0
    assert result.mismatched_observation_count == 0
    assert result.orphan_observation_count == 0


def test_surfaces_missing_mismatched_and_orphan_provider_observation_evidence():
    timestamp = datetime(2026, 1, 2, tzinfo=UTC)

    result = reconcile_ohlcv_storage(
        [
            _bar(ts=timestamp, source_id=7),
            _bar(ts=timestamp + timedelta(days=1), source_id=7),
        ],
        [
            _observation(ts=timestamp, source_id=7, close="12"),
            _observation(ts=timestamp + timedelta(days=2), source_id=7),
        ],
    )

    assert result.status == "inconsistent"
    assert result.provider_bar_count == 2
    assert result.observation_count == 2
    assert result.matched_observation_count == 0
    assert result.missing_observation_count == 1
    assert result.mismatched_observation_count == 1
    assert result.orphan_observation_count == 1


def test_reconciliation_keeps_timeframe_and_adjustment_views_distinct():
    timestamp = datetime(2026, 1, 2, tzinfo=UTC)

    result = reconcile_ohlcv_storage(
        [
            _bar(ts=timestamp, source_id=7, timeframe=Timeframe.D1, adjusted=True),
            _bar(ts=timestamp, source_id=7, timeframe=Timeframe.W1, adjusted=False),
        ],
        [
            _observation(ts=timestamp, source_id=7, timeframe=Timeframe.D1, adjusted=True),
            _observation(ts=timestamp, source_id=7, timeframe=Timeframe.W1, adjusted=False),
        ],
    )

    assert result.status == "reconciled"
    assert result.provider_bar_count == 2
    assert result.observation_count == 2
    assert result.matched_observation_count == 2
    assert result.missing_observation_count == 0
    assert result.mismatched_observation_count == 0
    assert result.orphan_observation_count == 0


def test_reconciliation_normalizes_offset_aware_observation_timestamps():
    result = reconcile_ohlcv_storage(
        [_bar(ts=datetime(2026, 1, 2, 0, 0, tzinfo=UTC), source_id=7)],
        [
            _observation(
                ts=datetime(2026, 1, 2, 1, 0, tzinfo=timezone(timedelta(hours=1))),
                source_id=7,
            )
        ],
    )

    assert result.status == "reconciled"
    assert result.matched_observation_count == 1


def test_reconciliation_counts_orphans_by_complete_identity():
    timestamp = datetime(2026, 1, 2, tzinfo=UTC)

    result = reconcile_ohlcv_storage(
        [_bar(ts=timestamp, source_id=7, timeframe=Timeframe.D1, adjusted=True)],
        [
            _observation(ts=timestamp, source_id=7, timeframe=Timeframe.W1, adjusted=True),
            _observation(ts=timestamp, source_id=7, timeframe=Timeframe.D1, adjusted=False),
        ],
    )

    assert result.status == "inconsistent"
    assert result.orphan_observation_count == 2
