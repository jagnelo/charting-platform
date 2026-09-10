from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.market_data_foundation import (
    MarketCoverageSnapshot,
    MarketDataAnomaly,
    ProviderShadowObservation,
)
from app.models.provider_runtime import ProviderCapability, ProviderCapacityEvent
from app.services.market_data_monitoring import (
    build_shadow_report,
    record_coverage_snapshot,
    record_market_data_anomaly,
    record_shadow_observation,
)
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_coverage_snapshot_reports_partial_without_fabricating_bars(db, instrument):
    async_db = AsyncSessionAdapter(db)
    at = datetime(2026, 9, 4, 16, tzinfo=UTC)
    row = await record_coverage_snapshot(
        async_db,
        instrument_id=instrument.id,
        market_series_id=None,
        timeframe="D1",
        expected_bars=10,
        observed_bars=8,
        evaluated_at=at,
        missing_slices=[{"start": "2026-09-03", "end": "2026-09-04"}],
    )
    assert row.status == "partial"
    assert row.coverage_ratio == Decimal("0.8")
    assert db.query(MarketCoverageSnapshot).count() == 1


@pytest.mark.asyncio
async def test_coverage_snapshots_without_series_remain_per_instrument(
    db, instrument, instrument_type
):
    from app.models.instrument import Instrument

    second = Instrument(
        symbol="MSFT",
        name="Microsoft Corp.",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    db.add(second)
    db.flush()
    async_db = AsyncSessionAdapter(db)
    at = datetime(2026, 9, 4, 16, tzinfo=UTC)
    for current in (instrument, second):
        await record_coverage_snapshot(
            async_db,
            instrument_id=current.id,
            market_series_id=None,
            timeframe="D1",
            expected_bars=1,
            observed_bars=1,
            evaluated_at=at,
        )

    assert db.query(MarketCoverageSnapshot).count() == 2


@pytest.mark.asyncio
async def test_shadow_report_is_explicitly_observational(db):
    async_db = AsyncSessionAdapter(db)
    at = datetime(2026, 9, 4, 16, tzinfo=UTC)
    await record_shadow_observation(
        async_db,
        request_key="shadow:1",
        capability="price_history",
        comparison_status="match",
        observed_at=at,
    )
    await record_shadow_observation(
        async_db,
        request_key="shadow:2",
        capability="price_history",
        comparison_status="discrepancy",
        discrepancy_metrics={"close_abs": 0.12},
        routing_enabled=False,
        observed_at=at + timedelta(minutes=1),
    )
    report = await build_shadow_report(async_db, since=at - timedelta(seconds=1))
    assert report["mode"] == "shadow_only"
    assert report["routing_enabled"] is False
    assert report["observations"] == 2
    assert report["discrepancies"] == 1
    assert db.query(ProviderShadowObservation).count() == 2
    assert report["core_daily_coverage"]["status"] == "insufficient_evidence"
    assert report["quota_capacity_events"]["count"] == 0
    assert report["open_anomalies"]["count"] == 0


@pytest.mark.asyncio
async def test_shadow_report_includes_daily_coverage_capacity_and_anomalies(db, instrument):
    async_db = AsyncSessionAdapter(db)
    at = datetime(2026, 9, 4, 16, tzinfo=UTC)
    await record_coverage_snapshot(
        async_db,
        instrument_id=instrument.id,
        market_series_id=None,
        timeframe="D1",
        expected_bars=100,
        observed_bars=99,
        evaluated_at=at,
        provenance={"source": "core_daily_coverage", "target_session": "2026-09-04"},
    )
    capacity = ProviderCapacityEvent(
        capability=ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv",
        error_type="ProviderRateLimitError",
        message="redacted capacity event",
        observed_at=at + timedelta(minutes=1),
    )
    db.add(capacity)
    await record_market_data_anomaly(
        async_db,
        anomaly_type="provider_close_mismatch",
        source="shadow",
        details={"close_abs": 0.12},
        severity="warning",
        detected_at=at + timedelta(minutes=2),
    )
    report = await build_shadow_report(async_db, since=at - timedelta(seconds=1))

    coverage = report["core_daily_coverage"]
    assert coverage["status"] == "pass"
    assert coverage["eligible_snapshots"] == 1
    assert coverage["expected_bars"] == 100
    assert coverage["observed_bars"] == 99
    assert coverage["coverage_ratio"] == pytest.approx(0.99)
    assert coverage["threshold_met"] is True
    assert report["quota_capacity_events"]["count"] == 1
    assert report["open_anomalies"] == {
        "count": 1,
        "by_severity": {"warning": 1},
    }


@pytest.mark.asyncio
async def test_anomaly_rows_coalesce_for_same_open_issue(db, instrument):
    async_db = AsyncSessionAdapter(db)
    at = datetime(2026, 9, 4, 16, tzinfo=UTC)
    first = await record_market_data_anomaly(
        async_db,
        anomaly_type="provider_close_mismatch",
        source="test",
        instrument_id=instrument.id,
        details={"first": 1},
        detected_at=at,
    )
    second = await record_market_data_anomaly(
        async_db,
        anomaly_type="provider_close_mismatch",
        source="test",
        instrument_id=instrument.id,
        details={"second": 2},
        detected_at=at + timedelta(hours=1),
    )
    assert first.id == second.id
    assert second.details == {"first": 1, "second": 2}
    assert db.query(MarketDataAnomaly).count() == 1
