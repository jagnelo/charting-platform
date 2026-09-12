from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.market_data_foundation import MarketRefreshJob
from app.models.ohlcv import OHLCVBar, Timeframe
from app.services.evaluator_preflight import preflight_ohlcv
from tests.unit.conftest import AsyncSessionAdapter


def _bars(instrument_id: int, start: datetime, count: int) -> list[OHLCVBar]:
    return [
        OHLCVBar(
            instrument_id=instrument_id,
            timeframe=Timeframe.D1,
            ts=start + timedelta(days=index),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            volume=Decimal("1000"),
            is_adjusted=True,
        )
        for index in range(count)
    ]


@pytest.mark.asyncio
async def test_preflight_reports_full_coverage_without_queueing(db, instrument):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    db.add_all(_bars(instrument.id, start, 5))
    db.flush()

    result = await preflight_ohlcv(
        AsyncSessionAdapter(db),
        evaluator="test_full",
        instrument_ids=[instrument.id],
        timeframe=Timeframe.D1,
        date_from=start,
        date_to=start + timedelta(days=4),
        now=start + timedelta(days=5),
    )

    assert result.status == "full"
    assert result.ready_instrument_ids == frozenset({instrument.id})
    assert result.queued_request_keys == ()
    assert result.items[0].missing_slices == ()


@pytest.mark.asyncio
async def test_preflight_queues_only_the_missing_tail(db, instrument):
    start = datetime(2026, 2, 1, tzinfo=UTC)
    db.add_all(_bars(instrument.id, start, 3))
    db.flush()

    result = await preflight_ohlcv(
        AsyncSessionAdapter(db),
        evaluator="test_tail",
        instrument_ids=[instrument.id],
        timeframe=Timeframe.D1,
        date_from=start,
        date_to=start + timedelta(days=4),
        queue_repairs=True,
        now=start + timedelta(days=5),
    )

    assert result.status == "deferred"
    assert result.ready_instrument_ids == frozenset()
    assert len(result.queued_request_keys) == 1
    item = result.items[0]
    assert item.status.value == "partial"
    assert item.missing_slices == (
        (start + timedelta(days=3), start + timedelta(days=4)),
    )
    job = (
        db.execute(select(MarketRefreshJob).where(MarketRefreshJob.request_key == result.queued_request_keys[0]))
    ).scalar_one()
    assert job.start_at == (start + timedelta(days=3)).replace(tzinfo=None)
    assert job.end_at == (start + timedelta(days=4)).replace(tzinfo=None)
    assert job.metadata_payload["evaluator"] == "test_tail"


@pytest.mark.asyncio
async def test_preflight_marks_latest_data_stale_without_inventing_provider_delay(db, instrument):
    start = datetime(2026, 3, 1, tzinfo=UTC)
    db.add_all(_bars(instrument.id, start, 3))
    db.flush()

    result = await preflight_ohlcv(
        AsyncSessionAdapter(db),
        evaluator="test_latest",
        instrument_ids=[instrument.id],
        timeframe=Timeframe.D1,
        date_from=start,
        date_to=start + timedelta(days=2),
        mode="latest",
        freshness_seconds=24 * 60 * 60,
        queue_repairs=True,
        now=start + timedelta(days=5),
    )

    assert result.status == "stale-blocked"
    assert result.ready_instrument_ids == frozenset()
    assert result.items[0].status.value == "stale"
    assert len(result.queued_request_keys) == 1


@pytest.mark.asyncio
async def test_preflight_is_partial_when_only_some_instruments_are_ready(
    db, instrument, instrument_b
):
    start = datetime(2026, 4, 1, tzinfo=UTC)
    db.add_all(_bars(instrument.id, start, 3))
    db.flush()

    result = await preflight_ohlcv(
        AsyncSessionAdapter(db),
        evaluator="test_partial",
        instrument_ids=[instrument.id, instrument_b.id],
        timeframe=Timeframe.D1,
        date_from=start,
        date_to=start + timedelta(days=2),
        now=start + timedelta(days=3),
    )

    assert result.status == "partial"
    assert result.ready_instrument_ids == frozenset({instrument.id})
    assert [item.status.value for item in result.items] == ["ready", "missing"]


@pytest.mark.asyncio
async def test_preflight_accepts_cached_bars_and_enforces_minimum_history(db, instrument):
    start = datetime(2026, 5, 1, tzinfo=UTC)
    cached = _bars(instrument.id, start, 2)

    result = await preflight_ohlcv(
        AsyncSessionAdapter(db),
        evaluator="test_cached",
        instrument_ids=[instrument.id],
        timeframe=Timeframe.D1,
        date_from=None,
        date_to=None,
        cached_bars={instrument.id: cached},
        minimum_bars=3,
        now=start + timedelta(days=2),
    )

    assert result.status == "deferred"
    assert result.items[0].status.value == "partial"
    assert result.items[0].bar_count == 2
    assert "at least 3" in result.items[0].explanation
