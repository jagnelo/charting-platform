import json
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.ohlcv import Timeframe
from app.services import bulk_fetch


@pytest.mark.asyncio
async def test_bulk_fetch_progress_uses_canonical_utc_z_timestamp():
    captured = {}

    class Redis:
        async def set(self, _key, payload, *, ex):
            captured.update(json.loads(payload))
            assert ex > 0

    await bulk_fetch._publish_progress(
        Redis(),
        42,
        "complete",
        [Timeframe.D1],
        {"D1": 3},
    )

    assert captured["updated_at"].endswith("Z")


@pytest.mark.asyncio
async def test_bulk_fetch_honours_refresh_cancellation_before_provider_work(monkeypatch):
    events = []

    class Redis:
        async def get(self, key):
            assert key == bulk_fetch.refresh_cancel_key(17)
            return "1"

    async def publish(_redis, instrument_id, status, _timeframes, _summary):
        events.append((instrument_id, status))

    monkeypatch.setattr(bulk_fetch, "_publish_progress", publish)
    result = await bulk_fetch.bulk_fetch_instrument(
        object(),
        SimpleNamespace(id=42, symbol="SPY"),
        [Timeframe.D1],
        redis=Redis(),
        cancel_key=bulk_fetch.refresh_cancel_key(17),
    )

    assert result == {}
    assert events == [(42, "canceled")]


@pytest.mark.asyncio
async def test_bulk_fetch_passes_historical_end_to_each_provider_request(monkeypatch):
    requested_ends = []

    async def fetch_one(*, end, **_kwargs):
        requested_ends.append(end)
        return 0

    monkeypatch.setattr(bulk_fetch, "_fetch_one_timeframe", fetch_one)
    await bulk_fetch.bulk_fetch_instrument(
        object(),
        SimpleNamespace(id=42, symbol="SPY"),
        [Timeframe.D1, Timeframe.W1],
        end=bulk_fetch.datetime(2024, 1, 2),
    )

    assert requested_ends == [
        bulk_fetch.datetime(2024, 1, 2, tzinfo=bulk_fetch.UTC),
        bulk_fetch.datetime(2024, 1, 2, tzinfo=bulk_fetch.UTC),
    ]


@pytest.mark.asyncio
async def test_bulk_fetch_does_not_skip_explicit_intraday_only_request(monkeypatch):
    calls = []

    async def fetch_one(*, timeframe, **_kwargs):
        calls.append(timeframe)
        return 0

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(bulk_fetch, "_fetch_one_timeframe", fetch_one)
    monkeypatch.setattr(bulk_fetch.asyncio, "sleep", no_sleep)

    result = await bulk_fetch.bulk_fetch_instrument(
        object(),
        SimpleNamespace(id=42, symbol="SPY"),
        [Timeframe.H1],
    )

    assert result == {"H1": 0}
    assert calls == [Timeframe.H1]


@pytest.mark.asyncio
async def test_bulk_fetch_custom_order_attempts_intraday_before_coarse_request(monkeypatch):
    calls = []

    async def fetch_one(*, timeframe, **_kwargs):
        calls.append(timeframe)
        return 1 if timeframe == Timeframe.D1 else 0

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(bulk_fetch, "_fetch_one_timeframe", fetch_one)
    monkeypatch.setattr(bulk_fetch.asyncio, "sleep", no_sleep)

    result = await bulk_fetch.bulk_fetch_instrument(
        object(),
        SimpleNamespace(id=42, symbol="SPY"),
        [Timeframe.H1, Timeframe.D1],
    )

    assert result == {"H1": 0, "D1": 1}
    assert calls == [Timeframe.H1, Timeframe.D1]


@pytest.mark.asyncio
async def test_bulk_fetch_does_not_skip_intraday_when_coarse_cache_has_only_duplicates(monkeypatch):
    calls = []

    class ScalarResult:
        def first(self):
            return 101

    class Result:
        def scalars(self):
            return ScalarResult()

    class Session:
        async def execute(self, _statement):
            return Result()

        async def commit(self):
            return None

    async def fetch_one(*, timeframe, **_kwargs):
        calls.append(timeframe)
        return 0

    async def materialize(*_args, **_kwargs):
        return {"W1": 0, "MN": 0}

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(bulk_fetch, "_fetch_one_timeframe", fetch_one)
    monkeypatch.setattr(bulk_fetch, "materialize_derived_timeframes", materialize)
    monkeypatch.setattr(bulk_fetch.asyncio, "sleep", no_sleep)

    result = await bulk_fetch.bulk_fetch_instrument(
        Session(),
        SimpleNamespace(id=42, symbol="SPY"),
        [Timeframe.D1, Timeframe.H1],
    )

    assert result == {"D1": 0, "H1": 0, "derived": {"W1": 0, "MN": 0}}
    assert calls == [Timeframe.D1, Timeframe.H1]


@pytest.mark.asyncio
async def test_bulk_fetch_still_skips_intraday_without_coarse_cache(monkeypatch):
    calls = []

    async def fetch_one(*, timeframe, **_kwargs):
        calls.append(timeframe)
        return 0

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(bulk_fetch, "_fetch_one_timeframe", fetch_one)
    monkeypatch.setattr(bulk_fetch.asyncio, "sleep", no_sleep)

    result = await bulk_fetch.bulk_fetch_instrument(
        object(),
        SimpleNamespace(id=42, symbol="SPY"),
        [Timeframe.D1, Timeframe.H1],
    )

    assert result == {"D1": 0, "H1": "skipped"}
    assert calls == [Timeframe.D1]


@pytest.mark.asyncio
async def test_bulk_fetch_passes_historical_end_to_derived_materializer(monkeypatch):
    materializer_ends = []

    class Session:
        async def commit(self):
            return None

        async def execute(self, *_args, **_kwargs):
            return None

    async def fetch_one(*, timeframe, **_kwargs):
        return 1 if timeframe == Timeframe.D1 else 0

    async def materialize(_db, _instrument_id, *, adjusted, end):
        materializer_ends.append((adjusted, end))
        return {"W1": 0, "MN": 0}

    async def no_sleep(_seconds):
        return None

    end = datetime(2024, 1, 2, tzinfo=UTC)
    monkeypatch.setattr(bulk_fetch, "_fetch_one_timeframe", fetch_one)
    monkeypatch.setattr(bulk_fetch, "materialize_derived_timeframes", materialize)
    monkeypatch.setattr(bulk_fetch.asyncio, "sleep", no_sleep)

    await bulk_fetch.bulk_fetch_instrument(
        Session(),
        SimpleNamespace(id=42, symbol="SPY"),
        [Timeframe.D1],
        end=end,
    )

    assert materializer_ends == [(True, end)]


@pytest.mark.asyncio
async def test_bounded_coarse_fetch_preserves_future_derived_rows(db, instrument, monkeypatch):
    from app.models.data_source import DataSource
    from app.models.ohlcv import OHLCVBar
    from tests.unit.conftest import AsyncSessionAdapter

    source = DataSource(name="bounded-coarse-provider")
    db.add(source)
    db.flush()

    future_ts = datetime(2025, 1, 6, tzinfo=UTC)
    db.add(
        OHLCVBar(
            instrument_id=instrument.id,
            timeframe=Timeframe.W1,
            ts=future_ts,
            open=Decimal("90"),
            high=Decimal("95"),
            low=Decimal("89"),
            close=Decimal("92"),
            volume=Decimal("100"),
            is_adjusted=True,
            is_derived=True,
            source_timeframe=Timeframe.D1.value,
            derivation_method="d1_ohlcv_xnys_calendar_aggregation",
            derived_at=datetime(2025, 1, 7, tzinfo=UTC),
            source_bar_count=5,
            source_start=datetime(2025, 1, 2, tzinfo=UTC),
            source_end=datetime(2025, 1, 6, tzinfo=UTC),
        )
    )
    db.flush()

    provider_bar = OHLCVBar(
        instrument_id=instrument.id,
        timeframe=Timeframe.W1,
        ts=datetime(2024, 1, 2, tzinfo=UTC),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("99"),
        close=Decimal("105"),
        volume=Decimal("200"),
        is_adjusted=True,
    )

    async def fake_execute(*_args, **_kwargs):
        return SimpleNamespace(
            result=[provider_bar],
            data_source=source,
            provider_name="bounded-coarse-provider",
        )

    async def no_record(*_args, **_kwargs):
        return None

    async def no_touch(*_args, **_kwargs):
        return None

    monkeypatch.setattr(bulk_fetch, "execute_provider_call", fake_execute)
    monkeypatch.setattr(bulk_fetch, "_record_bar_observations", no_record)
    monkeypatch.setattr(bulk_fetch, "_touch_ohlcv_dataset_state", no_touch)
    monkeypatch.setattr(bulk_fetch, "provider_symbol_for_instrument", lambda *_args: "AAPL")

    result = await bulk_fetch._do_fetch_and_store(
        db=AsyncSessionAdapter(db),
        instrument=instrument,
        ticker_sym=instrument.symbol,
        timeframe=Timeframe.W1,
        adjusted=True,
        end=datetime(2024, 1, 3, tzinfo=UTC),
    )

    assert result == 1
    rows = (
        db.query(OHLCVBar)
        .filter(
            OHLCVBar.instrument_id == instrument.id,
            OHLCVBar.timeframe == Timeframe.W1,
            OHLCVBar.is_adjusted.is_(True),
        )
        .order_by(OHLCVBar.ts)
        .all()
    )

    def as_utc(value):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    assert any(as_utc(row.ts) == future_ts and row.is_derived is True for row in rows)
    assert any(
        as_utc(row.ts) == datetime(2024, 1, 2, tzinfo=UTC)
        and row.data_source_id == source.id
        and row.is_derived is False
        for row in rows
    )


@pytest.mark.asyncio
async def test_bulk_fetch_raw_bars_materialize_provider_factors_after_event_first_refresh(
    db, instrument, monkeypatch
):
    from app.models.adjustment_factor import AdjustmentFactorObservation
    from app.models.data_source import DataSource
    from app.models.ohlcv import OHLCVBar
    from tests.unit.conftest import AsyncSessionAdapter

    source = DataSource(name="event-first-provider-factor")
    db.add(source)
    db.flush()
    db.add(
        AdjustmentFactorObservation(
            instrument_id=instrument.id,
            data_source_id=source.id,
            provider_symbol="AAPL",
            factor_type="dividend",
            effective_at=datetime(2024, 1, 3, tzinfo=UTC),
            factor=Decimal("0.9"),
            factor_kind="provider_supplied",
            source_event_key="dividend:event-first",
            observed_at=datetime(2024, 1, 4, tzinfo=UTC),
            factor_version="afv1-event-first",
        )
    )
    db.flush()

    provider_bars = [
        OHLCVBar(
            instrument_id=instrument.id,
            timeframe=Timeframe.D1,
            ts=datetime(2024, 1, 2, tzinfo=UTC),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("100"),
            volume=Decimal("200"),
            is_adjusted=False,
        ),
        OHLCVBar(
            instrument_id=instrument.id,
            timeframe=Timeframe.D1,
            ts=datetime(2024, 1, 4, tzinfo=UTC),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("100"),
            volume=Decimal("200"),
            is_adjusted=False,
        ),
    ]

    async def fake_execute(*_args, **_kwargs):
        return SimpleNamespace(
            result=provider_bars,
            data_source=source,
            provider_name="event-first-provider-factor",
        )

    async def no_record(*_args, **_kwargs):
        return None

    async def no_touch(*_args, **_kwargs):
        return None

    monkeypatch.setattr(bulk_fetch, "execute_provider_call", fake_execute)
    monkeypatch.setattr(bulk_fetch, "_record_bar_observations", no_record)
    monkeypatch.setattr(bulk_fetch, "_touch_ohlcv_dataset_state", no_touch)
    monkeypatch.setattr(bulk_fetch, "provider_symbol_for_instrument", lambda *_args: "AAPL")

    result = await bulk_fetch._do_fetch_and_store(
        db=AsyncSessionAdapter(db),
        instrument=instrument,
        ticker_sym=instrument.symbol,
        timeframe=Timeframe.D1,
        adjusted=False,
        end=datetime(2024, 1, 5, tzinfo=UTC),
    )

    assert result == 2
    derived = (
        db.query(OHLCVBar)
        .filter(
            OHLCVBar.instrument_id == instrument.id,
            OHLCVBar.timeframe == Timeframe.D1,
            OHLCVBar.is_adjusted.is_(True),
            OHLCVBar.is_derived.is_(True),
        )
        .filter(OHLCVBar.ts == datetime(2024, 1, 2, tzinfo=UTC))
        .one()
    )
    assert derived.close == Decimal("90.00000000")
    assert derived.derivation_method == "provider_adjustment_factor"


@pytest.mark.asyncio
async def test_bulk_fetch_treats_empty_provider_result_as_chain_failure(monkeypatch):
    calls = []

    async def fake_execute(*_args, **kwargs):
        calls.append(kwargs["treat_empty_as_failure"])
        return SimpleNamespace(result=[], data_source=SimpleNamespace(id=1))

    class Session:
        async def commit(self):
            return None

    async def touch_state(*_args, **_kwargs):
        return None

    monkeypatch.setattr(bulk_fetch, "execute_provider_call", fake_execute)
    monkeypatch.setattr(bulk_fetch, "_touch_ohlcv_dataset_state", touch_state)

    result = await bulk_fetch._do_fetch_and_store(
        db=Session(),
        instrument=SimpleNamespace(id=42, symbol="SPY"),
        ticker_sym="SPY",
        timeframe=Timeframe.D1,
        adjusted=True,
        end=bulk_fetch.datetime(2024, 1, 2, tzinfo=bulk_fetch.UTC),
    )

    assert result == 0
    assert calls == [True]


def test_bars_through_end_rejects_future_provider_rows():
    end = bulk_fetch.datetime(2024, 1, 2, tzinfo=bulk_fetch.UTC)
    bars = [
        SimpleNamespace(ts=bulk_fetch.datetime(2024, 1, 1)),
        SimpleNamespace(ts=bulk_fetch.datetime(2024, 1, 2, 23, 59)),
        SimpleNamespace(ts=bulk_fetch.datetime(2024, 1, 3)),
    ]

    assert bulk_fetch._bars_through_end(bars, end) == bars[:1]


def test_to_utc_normalizes_offset_aware_provider_timestamps():
    offset_timestamp = datetime(2024, 1, 2, 1, 0, tzinfo=timezone(timedelta(hours=1)))

    assert bulk_fetch._to_utc(offset_timestamp) == datetime(2024, 1, 2, tzinfo=UTC)
    assert bulk_fetch._to_utc(offset_timestamp).tzinfo == UTC
